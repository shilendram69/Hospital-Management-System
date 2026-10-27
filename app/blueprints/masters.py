"""
Master-data management.

The database starts completely empty - nothing is pre-loaded.  Everything the
hospital needs (departments, doctors, wards, beds, medicines, lab / radiology
catalogue, suppliers, inventory, staff) is entered here by the administrator
(or the responsible role).
"""
import re
from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (Admission, AuditLog, Bed, Department, Doctor, InventoryItem,
                        LabTest, Medicine, RadiologyTest, Staff, StockMovement, Supplier,
                        Transfer, User, Ward)

manage_bp = Blueprint('manage', __name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,80}$')
MIN_PASSWORD = 8
PER_PAGE = 25

STAFF_ROLES = [('nurse', 'Nurse'), ('receptionist', 'Receptionist'), ('pharmacist', 'Pharmacist'),
               ('lab_tech', 'Lab Technician'), ('radiologist', 'Radiologist'),
               ('admin', 'Administrator')]


# =====================================================================================
# helpers
# =====================================================================================
def audit(action, entity=None, entity_id=None, details=None):
    db.session.add(AuditLog(user_id=current_user.id, action=action, entity=entity,
                            entity_id=entity_id, details=details,
                            ip_address=request.remote_addr))


def F(name, label, type='text', **kw):
    """Field definition."""
    return dict(name=name, label=label, type=type, **kw)


def dept_options():
    return [(d.id, d.name) for d in Department.query.filter_by(is_active=True).order_by(Department.name)]


def doctor_options():
    rows = Doctor.query.join(User, Doctor.user_id == User.id).order_by(User.full_name).all()
    return [(d.id, d.user.full_name) for d in rows]


def ward_options():
    return [(w.id, w.name) for w in Ward.query.filter_by(is_active=True).order_by(Ward.name)]


def resolve_options(f):
    opts = f.get('options', [])
    return opts() if callable(opts) else opts


def parse_form(fields, form):
    """Validate + convert posted values. Returns (values, errors)."""
    values, errors = {}, []
    for f in fields:
        name, label, ftype = f['name'], f['label'], f.get('type', 'text')
        if ftype == 'checkbox':
            values[name] = bool(form.get(name))
            continue
        raw = (form.get(name) or '')
        if ftype != 'password':
            raw = raw.strip()
        if raw == '':
            if f.get('required'):
                errors.append(f'{label} is required.')
            values[name] = f.get('default')
            continue

        maxlen = f.get('maxlength')
        if maxlen and len(raw) > maxlen:
            errors.append(f'{label} must be at most {maxlen} characters.')
            continue

        try:
            if ftype == 'number':
                num = float(raw) if f.get('kind') == 'float' else int(raw)
                if f.get('min') is not None and num < f['min']:
                    errors.append(f'{label} must be at least {f["min"]}.')
                    continue
                if f.get('max') is not None and num > f['max']:
                    errors.append(f'{label} must be at most {f["max"]}.')
                    continue
                values[name] = num
            elif ftype == 'date':
                values[name] = datetime.strptime(raw, '%Y-%m-%d').date()
            elif ftype == 'email':
                if not EMAIL_RE.match(raw):
                    errors.append(f'{label} is not a valid email address.')
                    continue
                values[name] = raw.lower()
            elif ftype == 'select':
                allowed = {str(v): v for v, _ in resolve_options(f)}
                if raw not in allowed:
                    errors.append(f'Select a valid option for {label}.')
                    continue
                values[name] = allowed[raw]
            elif ftype == 'password':
                if len(raw) < MIN_PASSWORD:
                    errors.append(f'{label} must be at least {MIN_PASSWORD} characters.')
                    continue
                values[name] = raw
            else:
                values[name] = raw.upper() if f.get('upper') else raw
        except ValueError:
            errors.append(f'{label} has an invalid value.')
    return values, errors


def prep_fields(fields):
    """Resolve dynamic option lists for rendering."""
    out = []
    for f in fields:
        g = dict(f)
        if g.get('type') == 'select':
            g['options'] = resolve_options(f)
        out.append(g)
    return out


def obj_to_data(obj, fields):
    data = {}
    for f in fields:
        if f.get('virtual') or f['type'] == 'password':
            continue
        val = getattr(obj, f['name'], None)
        if isinstance(val, date):
            val = val.isoformat()
        data[f['name']] = '' if val is None else val
    return data


def default_data(fields):
    data = {}
    for f in fields:
        d = f.get('default')
        if f['type'] == 'checkbox':
            data[f['name']] = f.get('default', True)
        elif d is not None:
            data[f['name']] = d.isoformat() if isinstance(d, date) else d
    return data


def post_data(form, fields):
    data = form.to_dict()
    for f in fields:
        if f['type'] == 'checkbox':
            data[f['name']] = bool(form.get(f['name']))
    data.pop('password', None)
    data.pop('csrf_token', None)
    return data


def unique_taken(model, column, value, obj=None, ci=False):
    col = getattr(model, column)
    q = model.query.filter((func.lower(col) == value.lower()) if ci else (col == value))
    if obj is not None:
        q = q.filter(model.id != obj.id)
    return q.first() is not None


def sync_ward_totals():
    for w in Ward.query.all():
        w.total_beds = w.beds.count()


# =====================================================================================
# entity configuration
# =====================================================================================
def _ward_after_save(ward, values, is_new):
    if is_new and (values.get('bed_count') or 0) > 0:
        prefix = (values.get('bed_prefix') or re.sub(r'[^A-Za-z0-9]', '', ward.name)[:3] or 'BED').upper()
        for i in range(1, values['bed_count'] + 1):
            db.session.add(Bed(bed_number=f'{prefix}-{i:02d}', ward_id=ward.id, status='Available',
                               bed_type=values.get('bed_type') or 'Standard',
                               daily_charge=values.get('daily_charge') or 0))
        db.session.flush()
    ward.total_beds = ward.beds.count()


def _ward_validate(values, obj):
    errs = []
    q = Ward.query.filter(func.lower(Ward.name) == (values.get('name') or '').lower())
    if obj is not None:
        q = q.filter(Ward.id != obj.id)
    if values.get('name') and q.first():
        errs.append('A ward with this name already exists.')
    return errs


def _bed_validate(values, obj):
    errs = []
    if values.get('ward_id') and values.get('bed_number'):
        q = Bed.query.filter(Bed.ward_id == values['ward_id'],
                             func.lower(Bed.bed_number) == values['bed_number'].lower())
        if obj is not None:
            q = q.filter(Bed.id != obj.id)
        if q.first():
            errs.append('This bed number already exists in the selected ward.')
    return errs


def _bed_can_delete(bed):
    if bed.status == 'Occupied':
        return False, 'An occupied bed cannot be deleted.'
    if Admission.query.filter_by(bed_id=bed.id).first() or \
            Transfer.query.filter((Transfer.from_bed_id == bed.id) | (Transfer.to_bed_id == bed.id)).first():
        return False, 'This bed has admission history. Set its status to Maintenance instead.'
    return True, ''


def _medicine_after_save(med, values, is_new):
    if is_new and (med.current_stock or 0) > 0:
        db.session.add(StockMovement(medicine_id=med.id, movement_type='IN', quantity=med.current_stock,
                                     reference='OPENING', notes='Opening stock', performed_by=current_user.id))


def _doctor_search(q):
    like = f'%{q}%'
    return db.or_(Doctor.specialization.ilike(like), Doctor.qualification.ilike(like),
                  Doctor.license_number.ilike(like), Doctor.user.has(User.full_name.ilike(like)))


def _staff_search(q):
    like = f'%{q}%'
    return db.or_(Staff.employee_id.ilike(like), Staff.designation.ilike(like),
                  Staff.user.has(User.full_name.ilike(like)))


def _yn(v):
    return 'Active' if v else 'Inactive'


ENTITIES = {}


def register(key, **cfg):
    cfg.setdefault('roles', ('admin',))
    cfg.setdefault('toggle', 'is_active')
    ENTITIES[key] = cfg


register(
    'departments', model=Department, singular='Department', plural='Departments', icon='bi-diagram-3',
    desc='Clinical and support departments (Cardiology, Pediatrics, ...).',
    order=[Department.name], search=['name', 'description'],
    columns=[('Name', lambda o: o.name),
             ('Description', lambda o: (o.description or '-')[:70]),
             ('Doctors', lambda o: o.doctors.count()),
             ('Status', lambda o: _yn(o.is_active))],
    fields=[F('name', 'Department name', required=True, maxlength=100, unique=True, ci=True),
            F('description', 'Description', 'textarea', col=12),
            F('head_doctor_id', 'Head of department', 'select', options=doctor_options, edit_only=True,
              help='Choose after doctors have been added.'),
            F('is_active', 'Active', 'checkbox')],
)

register(
    'wards', model=Ward, singular='Ward', plural='Wards', icon='bi-building',
    desc='Wards / rooms. You can auto-create beds while adding a ward.',
    roles=('admin',), order=[Ward.name], search=['name', 'ward_type'],
    columns=[('Ward', lambda o: o.name),
             ('Department', lambda o: o.department.name if o.department else '-'),
             ('Type', lambda o: o.ward_type or '-'),
             ('Total beds', lambda o: o.beds.count()),
             ('Available', lambda o: o.available_beds),
             ('Status', lambda o: _yn(o.is_active))],
    fields=[F('name', 'Ward name', required=True, maxlength=50),
            F('department_id', 'Department', 'select', options=dept_options),
            F('ward_type', 'Ward type', 'select', required=True,
              options=[(t, t) for t in ('General', 'Semi-Private', 'Private', 'ICU', 'Emergency',
                                        'Pediatric', 'Maternity', 'Other')]),
            F('is_active', 'Active', 'checkbox'),
            F('bed_count', 'Create beds now (how many?)', 'number', create_only=True, virtual=True,
              default=0, min=0, max=500, section='Quick bed creation (optional)',
              help='Beds are numbered automatically, e.g. GEN-01, GEN-02 ...'),
            F('bed_prefix', 'Bed number prefix', create_only=True, virtual=True, maxlength=10,
              upper=True, help='Leave blank to use the first 3 letters of the ward name.'),
            F('bed_type', 'Bed type', 'select', create_only=True, virtual=True, default='Standard',
              options=[(t, t) for t in ('Standard', 'ICU', 'Ventilator')]),
            F('daily_charge', 'Daily charge per bed (₹)', 'number', kind='float', min=0, default=0,
              create_only=True, virtual=True)],
    validate=_ward_validate, after_save=_ward_after_save,
)

register(
    'beds', model=Bed, singular='Bed', plural='Beds', icon='bi-grid-3x3-gap',
    desc='Individual beds and their daily charges.',
    roles=('admin',), order=[Bed.ward_id, Bed.bed_number], search=['bed_number'],
    toggle=None, deletable=True,
    columns=[('Bed', lambda o: o.bed_number),
             ('Ward', lambda o: o.ward.name if o.ward else '-'),
             ('Type', lambda o: o.bed_type or '-'),
             ('Daily charge', lambda o: f'₹{o.daily_charge or 0:,.2f}'),
             ('Status', lambda o: o.status)],
    fields=[F('ward_id', 'Ward', 'select', required=True, options=ward_options),
            F('bed_number', 'Bed number', required=True, maxlength=20, upper=True),
            F('bed_type', 'Bed type', 'select', required=True, default='Standard',
              options=[(t, t) for t in ('Standard', 'ICU', 'Ventilator')]),
            F('daily_charge', 'Daily charge (₹)', 'number', kind='float', min=0, required=True, default=0),
            F('status', 'Status', 'select', required=True, default='Available',
              options=[(t, t) for t in ('Available', 'Maintenance', 'Reserved')])],
    validate=_bed_validate, can_delete=_bed_can_delete, after_save=lambda o, v, n: sync_ward_totals(),
    after_delete=lambda: sync_ward_totals(),
    skip_fields=lambda o: {'status'} if (o is not None and o.status == 'Occupied') else set(),
    form_note=lambda o: 'This bed is currently occupied - its status changes automatically on discharge/transfer.'
    if (o is not None and o.status == 'Occupied') else None,
)

register(
    'medicines', model=Medicine, singular='Medicine', plural='Medicines', icon='bi-capsule',
    desc='Pharmacy medicine master. Stock is increased later through "Stock In".',
    roles=('admin', 'pharmacist'), order=[Medicine.name], search=['name', 'generic_name', 'category', 'manufacturer'],
    columns=[('Name', lambda o: o.name),
             ('Generic', lambda o: o.generic_name or '-'),
             ('Category', lambda o: o.category or '-'),
             ('Stock', lambda o: f'{o.current_stock or 0} {o.unit or ""}'),
             ('Selling price', lambda o: f'₹{o.selling_price or 0:,.2f}'),
             ('Status', lambda o: _yn(o.is_active))],
    fields=[F('name', 'Medicine name', required=True, maxlength=150),
            F('generic_name', 'Generic name', maxlength=150),
            F('category', 'Category', maxlength=50, help='e.g. Antibiotic, Analgesic'),
            F('manufacturer', 'Manufacturer', maxlength=100),
            F('unit', 'Form / unit', 'select', required=True, default='Tablet',
              options=[(t, t) for t in ('Tablet', 'Capsule', 'Syrup', 'Injection', 'Ointment', 'Drops',
                                        'Sachet', 'Inhaler', 'Other')]),
            F('strength', 'Strength', maxlength=50, help='e.g. 500mg'),
            F('unit_price', 'Purchase price (₹)', 'number', kind='float', min=0, default=0),
            F('selling_price', 'Selling price (₹)', 'number', kind='float', min=0, default=0),
            F('reorder_level', 'Reorder level', 'number', min=0, default=10),
            F('current_stock', 'Opening stock', 'number', min=0, default=0, create_only=True),
            F('requires_prescription', 'Requires prescription', 'checkbox'),
            F('is_active', 'Active', 'checkbox'),
            F('description', 'Description', 'textarea', col=12)],
    after_save=_medicine_after_save,
)

register(
    'suppliers', model=Supplier, singular='Supplier', plural='Suppliers', icon='bi-truck',
    desc='Medicine / equipment suppliers used in stock-in.',
    roles=('admin', 'pharmacist'), order=[Supplier.name], search=['name', 'contact_person', 'phone'],
    columns=[('Supplier', lambda o: o.name),
             ('Contact', lambda o: o.contact_person or '-'),
             ('Phone', lambda o: o.phone or '-'),
             ('Email', lambda o: o.email or '-'),
             ('Status', lambda o: _yn(o.is_active))],
    fields=[F('name', 'Supplier name', required=True, maxlength=150),
            F('contact_person', 'Contact person', maxlength=100),
            F('phone', 'Phone', maxlength=20),
            F('email', 'Email', 'email', maxlength=120),
            F('gstin', 'GSTIN', maxlength=20, upper=True),
            F('is_active', 'Active', 'checkbox'),
            F('address', 'Address', 'textarea', col=12)],
)

register(
    'lab_tests', model=LabTest, singular='Lab Test', plural='Lab Tests', icon='bi-eyedropper',
    desc='Laboratory test catalogue with price and turnaround time.',
    roles=('admin', 'lab_tech'), order=[LabTest.category, LabTest.name], search=['name', 'code', 'category'],
    columns=[('Code', lambda o: o.code or '-'),
             ('Test', lambda o: o.name),
             ('Category', lambda o: o.category or '-'),
             ('Sample', lambda o: o.sample_type or '-'),
             ('Price', lambda o: f'₹{o.price or 0:,.2f}'),
             ('TAT', lambda o: f'{o.turnaround_hours or 0} h'),
             ('Status', lambda o: _yn(o.is_active))],
    fields=[F('name', 'Test name', required=True, maxlength=150),
            F('code', 'Test code', required=True, maxlength=20, upper=True, unique=True,
              help='Short unique code, e.g. CBC'),
            F('category', 'Category', maxlength=50, help='Hematology, Biochemistry, ...'),
            F('sample_type', 'Sample type', maxlength=50, help='Blood, Urine, ...'),
            F('price', 'Price (₹)', 'number', kind='float', min=0, required=True, default=0),
            F('turnaround_hours', 'Turnaround time (hours)', 'number', min=0, default=24),
            F('normal_range', 'Normal / reference range', maxlength=100),
            F('unit', 'Result unit', maxlength=30),
            F('is_active', 'Active', 'checkbox'),
            F('description', 'Description', 'textarea', col=12)],
)

register(
    'radiology_tests', model=RadiologyTest, singular='Radiology Test', plural='Radiology Tests',
    icon='bi-activity', desc='Imaging catalogue (X-Ray, CT, MRI, Ultrasound ...).',
    roles=('admin', 'radiologist'), order=[RadiologyTest.modality, RadiologyTest.name],
    search=['name', 'modality', 'body_part'],
    columns=[('Test', lambda o: o.name),
             ('Modality', lambda o: o.modality or '-'),
             ('Body part', lambda o: o.body_part or '-'),
             ('Price', lambda o: f'₹{o.price or 0:,.2f}'),
             ('Duration', lambda o: f'{o.duration_minutes or 0} min'),
             ('Status', lambda o: _yn(o.is_active))],
    fields=[F('name', 'Test name', required=True, maxlength=150),
            F('modality', 'Modality', 'select', required=True,
              options=[(t, t) for t in ('X-Ray', 'CT', 'MRI', 'Ultrasound', 'Mammography',
                                        'Fluoroscopy', 'Other')]),
            F('body_part', 'Body part', maxlength=50),
            F('price', 'Price (₹)', 'number', kind='float', min=0, required=True, default=0),
            F('duration_minutes', 'Duration (minutes)', 'number', min=1, default=30),
            F('is_active', 'Active', 'checkbox')],
)

register(
    'inventory', model=InventoryItem, singular='Inventory Item', plural='Inventory',
    icon='bi-box-seam', desc='Equipment and consumables (gloves, syringes, monitors ...).',
    roles=('admin', 'nurse'), order=[InventoryItem.category, InventoryItem.name],
    search=['name', 'item_code', 'category', 'location'],
    columns=[('Code', lambda o: o.item_code or '-'),
             ('Item', lambda o: o.name),
             ('Category', lambda o: o.category or '-'),
             ('Stock', lambda o: f'{o.current_stock or 0} {o.unit or ""}'),
             ('Location', lambda o: o.location or '-'),
             ('Status', lambda o: _yn(o.is_active))],
    fields=[F('name', 'Item name', required=True, maxlength=150),
            F('item_code', 'Item code', required=True, maxlength=30, upper=True, unique=True),
            F('category', 'Category', 'select', required=True,
              options=[(t, t) for t in ('Equipment', 'Consumable', 'Surgical', 'Linen', 'Other')]),
            F('unit', 'Unit', maxlength=20, help='Box, Piece, Unit ...'),
            F('current_stock', 'Current stock', 'number', min=0, default=0),
            F('reorder_level', 'Reorder level', 'number', min=0, default=10),
            F('unit_cost', 'Unit cost (₹)', 'number', kind='float', min=0, default=0),
            F('location', 'Location', maxlength=50, help='Store, Ward, OT ...'),
            F('is_active', 'Active', 'checkbox'),
            F('description', 'Description', 'textarea', col=12)],
)


# =====================================================================================
# doctors (User account + Doctor profile)
# =====================================================================================
def _doctor_fields(is_new):
    return [
        F('full_name', 'Full name', required=True, maxlength=150, section='Login account',
          help='Shown as "Dr. ..." exactly as typed.'),
        F('username', 'Username', required=True, maxlength=80, create_only=True),
        F('email', 'Email', 'email', required=True, maxlength=120),
        F('phone', 'Phone', maxlength=20),
        F('password', 'Password' if is_new else 'New password', 'password', required=is_new, virtual=True,
          help='Minimum 8 characters.' if is_new else 'Leave blank to keep the current password.'),
        F('department_id', 'Department', 'select', required=True, options=dept_options,
          section='Professional details',
          help='No department listed? Add one first under Departments.'),
        F('specialization', 'Specialization', required=True, maxlength=100),
        F('qualification', 'Qualification', maxlength=200, help='MBBS, MD ...'),
        F('experience_years', 'Experience (years)', 'number', min=0, max=70, default=0),
        F('consultation_fee', 'Consultation fee (₹)', 'number', kind='float', min=0, default=0, required=True),
        F('license_number', 'Medical license number', maxlength=50),
        F('availability', 'Availability / timings', maxlength=200, help='e.g. Mon-Sat 9:00-14:00'),
        F('is_available', 'Available for appointments', 'checkbox'),
        F('bio', 'Short bio', 'textarea', col=12),
    ]


def doctor_form(e, key, doc):
    is_new = doc is None
    fields = [f for f in _doctor_fields(is_new) if not (f.get('create_only') and not is_new)]
    user = None if is_new else doc.user

    if request.method == 'POST':
        values, errors = parse_form(fields, request.form)
        if not errors:
            if 'username' in values:
                if not USERNAME_RE.match(values['username'] or ''):
                    errors.append('Username must be 3-80 characters (letters, numbers, . _ -).')
                elif unique_taken(User, 'username', values['username'], ci=True):
                    errors.append('This username is already taken.')
            if unique_taken(User, 'email', values['email'], obj=user, ci=True):
                errors.append('This email is already used by another account.')
            if values.get('license_number') and unique_taken(Doctor, 'license_number', values['license_number'], obj=doc):
                errors.append('This license number is already registered.')
        if not errors:
            try:
                if is_new:
                    user = User(username=values['username'], role='doctor')
                    db.session.add(user)
                    doc = Doctor()
                    doc.user = user
                    db.session.add(doc)
                user.full_name = values['full_name']
                user.email = values['email']
                user.phone = values.get('phone')
                if values.get('password'):
                    user.set_password(values['password'])
                for name in ('department_id', 'specialization', 'qualification', 'experience_years',
                             'consultation_fee', 'license_number', 'availability', 'is_available', 'bio'):
                    setattr(doc, name, values.get(name))
                db.session.flush()
                audit('CREATE_DOCTOR' if is_new else 'UPDATE_DOCTOR', 'Doctor', doc.id,
                      f'{"Added" if is_new else "Updated"} doctor {user.full_name}')
                db.session.commit()
                flash(f'Doctor {user.full_name} {"added" if is_new else "updated"} successfully.', 'success')
                return redirect(url_for('manage.list_entity', entity=key))
            except IntegrityError:
                db.session.rollback()
                flash('Could not save: username, email or license number already exists.', 'danger')
        else:
            for err in errors:
                flash(err, 'danger')
        data = post_data(request.form, fields)
    elif is_new:
        data = default_data(fields)
    else:
        data = obj_to_data(doc, [f for f in fields if f['name'] in
                                 ('department_id', 'specialization', 'qualification', 'experience_years',
                                  'consultation_fee', 'license_number', 'availability', 'is_available', 'bio')])
        data.update(full_name=user.full_name, email=user.email, phone=user.phone or '', username=user.username)

    return render_template('manage/form.html', e=e, key=key, fields=prep_fields(fields), data=data,
                           obj=doc, is_new=is_new, note=None)


register(
    'doctors', model=Doctor, singular='Doctor', plural='Doctors', icon='bi-person-badge',
    desc='Doctor profiles with their login accounts.',
    toggle='is_available', toggle_labels=('Mark unavailable', 'Mark available'),
    order=[Doctor.id], search=_doctor_search, form_handler=doctor_form,
    columns=[('Name', lambda o: o.user.full_name if o.user else '-'),
             ('Department', lambda o: o.department.name if o.department else '-'),
             ('Specialization', lambda o: o.specialization or '-'),
             ('Fee', lambda o: f'₹{o.consultation_fee or 0:,.2f}'),
             ('Login', lambda o: o.user.username if o.user else '-'),
             ('Status', lambda o: 'Available' if o.is_available else 'Unavailable')],
)


# =====================================================================================
# staff (User account + Staff profile)
# =====================================================================================
def _linkable_users():
    rows = (User.query.outerjoin(Staff, Staff.user_id == User.id)
            .filter(Staff.id.is_(None), User.role != 'doctor').order_by(User.full_name).all())
    return [(u.id, f'{u.full_name} ({u.username})') for u in rows]


def _next_employee_id():
    n = (db.session.query(func.coalesce(func.max(Staff.id), 0)).scalar() or 0) + 1
    while Staff.query.filter_by(employee_id=f'EMP-{n:04d}').first():
        n += 1
    return f'EMP-{n:04d}'


def _staff_fields(is_new):
    fields = []
    if is_new:
        fields.append(F('existing_user_id', 'Use an existing user account', 'select', options=_linkable_users,
                        virtual=True, section='Login account',
                        help='Optional. Leave blank to create a new login below.'))
    fields += [
        F('full_name', 'Full name', maxlength=150, section=None if is_new else 'Login account'),
        F('username', 'Username', maxlength=80, create_only=True),
        F('email', 'Email', 'email', maxlength=120),
        F('phone', 'Phone', maxlength=20),
        F('role', 'Role', 'select', options=STAFF_ROLES, default='nurse'),
        F('password', 'Password' if is_new else 'New password', 'password', virtual=True,
          help='Minimum 8 characters.' if is_new else 'Leave blank to keep the current password.'),
        F('employee_id', 'Employee ID', maxlength=20, upper=True, section='Employment',
          help='Leave blank to auto-generate (EMP-0001 ...).'),
        F('designation', 'Designation', required=True, maxlength=50, help='Staff Nurse, Technician ...'),
        F('department_id', 'Department', 'select', options=dept_options),
        F('joining_date', 'Joining date', 'date', default=date.today()),
        F('shift', 'Shift', 'select', default='Morning',
          options=[(t, t) for t in ('Morning', 'Evening', 'Night', 'Rotational')]),
        F('salary', 'Monthly salary (₹)', 'number', kind='float', min=0),
        F('is_active', 'Active', 'checkbox'),
    ]
    return fields


def staff_form(e, key, staff):
    is_new = staff is None
    fields = [f for f in _staff_fields(is_new) if not (f.get('create_only') and not is_new)]
    user = None if is_new else staff.user
    profile_names = ('employee_id', 'designation', 'department_id', 'joining_date', 'shift', 'salary', 'is_active')

    if request.method == 'POST':
        values, errors = parse_form(fields, request.form)
        existing = values.get('existing_user_id') if is_new else None
        if not errors:
            if existing:
                user = db.session.get(User, existing)
            else:
                for name, label in (('full_name', 'Full name'), ('email', 'Email'), ('role', 'Role')):
                    if not values.get(name):
                        errors.append(f'{label} is required.')
                if is_new:
                    if not USERNAME_RE.match(values.get('username') or ''):
                        errors.append('Username must be 3-80 characters (letters, numbers, . _ -).')
                    elif unique_taken(User, 'username', values['username'], ci=True):
                        errors.append('This username is already taken.')
                    if not values.get('password'):
                        errors.append('Password is required for a new login.')
                if values.get('email') and unique_taken(User, 'email', values['email'], obj=user, ci=True):
                    errors.append('This email is already used by another account.')
            emp = values.get('employee_id')
            if emp and unique_taken(Staff, 'employee_id', emp, obj=staff):
                errors.append('This employee ID already exists.')
        if not errors:
            try:
                # generate before adding anything to the session (autoflush would consume an id)
                emp_id = values.get('employee_id') or (None if staff is not None and staff.employee_id else _next_employee_id())
                if is_new:
                    if not existing:
                        user = User(username=values['username'])
                        db.session.add(user)
                    staff = Staff()
                    staff.user = user
                    db.session.add(staff)
                if not existing:
                    user.full_name = values['full_name']
                    user.email = values['email']
                    user.phone = values.get('phone')
                    user.role = values['role']
                    if values.get('password'):
                        user.set_password(values['password'])
                for name in profile_names:
                    if name != 'employee_id':
                        setattr(staff, name, values.get(name))
                if emp_id:
                    staff.employee_id = emp_id
                db.session.flush()
                audit('CREATE_STAFF' if is_new else 'UPDATE_STAFF', 'Staff', staff.id,
                      f'{"Added" if is_new else "Updated"} staff {user.full_name}')
                db.session.commit()
                flash(f'Staff member {user.full_name} {"added" if is_new else "updated"} successfully.', 'success')
                return redirect(url_for('manage.list_entity', entity=key))
            except IntegrityError:
                db.session.rollback()
                flash('Could not save: username, email or employee ID already exists.', 'danger')
        else:
            for err in errors:
                flash(err, 'danger')
        data = post_data(request.form, fields)
    elif is_new:
        data = default_data(fields)
    else:
        data = obj_to_data(staff, [f for f in fields if f['name'] in profile_names])
        data.update(full_name=user.full_name, email=user.email, phone=user.phone or '', role=user.role,
                    username=user.username)

    return render_template('manage/form.html', e=e, key=key, fields=prep_fields(fields), data=data,
                           obj=staff, is_new=is_new, note=None)


register(
    'staff', model=Staff, singular='Staff Member', plural='Staff', icon='bi-person-workspace',
    desc='Employees (nurses, receptionists, technicians ...) with login accounts.',
    order=[Staff.id], search=_staff_search, form_handler=staff_form,
    columns=[('Employee ID', lambda o: o.employee_id or '-'),
             ('Name', lambda o: o.user.full_name if o.user else '-'),
             ('Role', lambda o: (o.user.role or '').replace('_', ' ').title() if o.user else '-'),
             ('Designation', lambda o: o.designation or '-'),
             ('Department', lambda o: o.department.name if o.department else '-'),
             ('Shift', lambda o: o.shift or '-'),
             ('Status', lambda o: _yn(o.is_active))],
)


# =====================================================================================
# generic views
# =====================================================================================
def _entity(key):
    e = ENTITIES.get(key)
    if not e:
        abort(404)
    if current_user.role != 'admin' and current_user.role not in e['roles']:
        abort(403)
    return e


def _generic_form(e, key, obj):
    is_new = obj is None
    skip = e['skip_fields'](obj) if e.get('skip_fields') else set()
    fields = [f for f in e['fields']
              if not (f.get('create_only') and not is_new)
              and not (f.get('edit_only') and is_new)
              and f['name'] not in skip]

    if request.method == 'POST':
        values, errors = parse_form(fields, request.form)
        if not errors:
            for f in fields:
                if f.get('unique') and values.get(f['name']):
                    if unique_taken(e['model'], f['name'], values[f['name']], obj=obj, ci=f.get('ci', False)):
                        errors.append(f'{f["label"]} "{values[f["name"]]}" already exists.')
            if e.get('validate'):
                errors += e['validate'](values, obj)
        if not errors:
            try:
                if is_new:
                    obj = e['model']()
                    db.session.add(obj)
                for f in fields:
                    if not f.get('virtual'):
                        setattr(obj, f['name'], values[f['name']])
                db.session.flush()
                if e.get('after_save'):
                    e['after_save'](obj, values, is_new)
                label = getattr(obj, 'name', None) or getattr(obj, 'bed_number', None) or obj.id
                audit(f'{"CREATE" if is_new else "UPDATE"}_{key.upper()}', e['model'].__name__, obj.id,
                      f'{"Added" if is_new else "Updated"} {e["singular"].lower()} {label}')
                db.session.commit()
                flash(f'{e["singular"]} "{label}" {"added" if is_new else "updated"} successfully.', 'success')
                return redirect(url_for('manage.list_entity', entity=key))
            except IntegrityError:
                db.session.rollback()
                flash('Could not save: a record with the same unique value already exists.', 'danger')
        else:
            for err in errors:
                flash(err, 'danger')
        data = post_data(request.form, fields)
    elif is_new:
        data = default_data(fields)
    else:
        data = obj_to_data(obj, fields)

    note = e['form_note'](obj) if e.get('form_note') else None
    return render_template('manage/form.html', e=e, key=key, fields=prep_fields(fields), data=data,
                           obj=obj, is_new=is_new, note=note)


@manage_bp.route('/')
@login_required
def hub():
    cards = []
    for key, e in ENTITIES.items():
        if current_user.role != 'admin' and current_user.role not in e['roles']:
            continue
        cards.append(dict(key=key, e=e, count=e['model'].query.count()))
    steps = get_setup_steps() if current_user.role == 'admin' else []
    return render_template('manage/index.html', cards=cards, steps=steps)


@manage_bp.route('/<entity>/')
@login_required
def list_entity(entity):
    e = _entity(entity)
    q = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    query = e['model'].query
    if q and e.get('search'):
        s = e['search']
        if callable(s):
            query = query.filter(s(q))
        else:
            query = query.filter(db.or_(*[getattr(e['model'], a).ilike(f'%{q}%') for a in s]))
    pagination = query.order_by(*e['order']).paginate(page=page, per_page=PER_PAGE, error_out=False)
    return render_template('manage/list.html', e=e, key=entity, pagination=pagination, q=q)


@manage_bp.route('/<entity>/new', methods=['GET', 'POST'])
@login_required
def create_entity(entity):
    e = _entity(entity)
    return (e.get('form_handler') or _generic_form)(e, entity, None)


@manage_bp.route('/<entity>/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_entity(entity, id):
    e = _entity(entity)
    obj = e['model'].query.get_or_404(id)
    return (e.get('form_handler') or _generic_form)(e, entity, obj)


@manage_bp.route('/<entity>/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_entity(entity, id):
    e = _entity(entity)
    attr = e.get('toggle')
    if not attr:
        abort(404)
    obj = e['model'].query.get_or_404(id)
    new_value = not getattr(obj, attr)
    setattr(obj, attr, new_value)
    audit(f'TOGGLE_{entity.upper()}', e['model'].__name__, obj.id, f'{attr} set to {new_value}')
    db.session.commit()
    flash(f'{e["singular"]} updated.', 'success')
    return redirect(request.referrer or url_for('manage.list_entity', entity=entity))


@manage_bp.route('/<entity>/<int:id>/delete', methods=['POST'])
@login_required
def delete_entity(entity, id):
    e = _entity(entity)
    if not e.get('deletable'):
        abort(404)
    obj = e['model'].query.get_or_404(id)
    ok, msg = e['can_delete'](obj)
    if not ok:
        flash(msg, 'warning')
    else:
        try:
            audit(f'DELETE_{entity.upper()}', e['model'].__name__, obj.id, f'Deleted {e["singular"].lower()}')
            db.session.delete(obj)
            db.session.flush()
            if e.get('after_delete'):
                e['after_delete']()
            db.session.commit()
            flash(f'{e["singular"]} deleted.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('This record is in use and cannot be deleted.', 'danger')
    return redirect(request.referrer or url_for('manage.list_entity', entity=entity))


# =====================================================================================
# setup checklist + contextual shortcuts
# =====================================================================================
def get_setup_steps():
    """Ordered checklist shown on the Setup hub and as a dashboard reminder."""
    return [
        dict(key='departments', label='Add departments', done=Department.query.first() is not None),
        dict(key='doctors', label='Add doctors', done=Doctor.query.first() is not None),
        dict(key='wards', label='Add wards', done=Ward.query.first() is not None),
        dict(key='beds', label='Add beds', done=Bed.query.first() is not None),
        dict(key='lab_tests', label='Add lab tests', done=LabTest.query.first() is not None),
        dict(key='radiology_tests', label='Add radiology tests', done=RadiologyTest.query.first() is not None),
        dict(key='medicines', label='Add medicines', done=Medicine.query.first() is not None),
        dict(key='staff', label='Add staff', done=Staff.query.first() is not None),
    ]


_SHORTCUTS = {
    'doctors.list_doctors': ['doctors'],
    'doctors.departments': ['departments'],
    'lab.tests': ['lab_tests'],
    'radiology.tests': ['radiology_tests'],
    'pharmacy.list_medicines': ['medicines', 'suppliers'],
    'inventory.list_items': ['inventory'],
    'staff.list_staff': ['staff'],
    'adt.beds': ['wards', 'beds'],
}


def shortcuts_for(endpoint):
    """Add/Manage buttons injected on the existing list pages for permitted users."""
    out = []
    for key in _SHORTCUTS.get(endpoint, []):
        e = ENTITIES[key]
        if current_user.role != 'admin' and current_user.role not in e['roles']:
            continue
        out.append(dict(label=f'Manage {e["plural"]}', singular=e['singular'],
                        url=url_for('manage.list_entity', entity=key),
                        add_url=url_for('manage.create_entity', entity=key)))
    return out
