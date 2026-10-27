import re
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import AuditLog, Doctor, User

admin_bp = Blueprint('admin', __name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,80}$')
MIN_PASSWORD = 8
ROLES = [('receptionist', 'Receptionist'), ('doctor', 'Doctor'), ('nurse', 'Nurse'),
         ('pharmacist', 'Pharmacist'), ('lab_tech', 'Lab Technician'),
         ('radiologist', 'Radiologist'), ('admin', 'Administrator')]
VALID_ROLES = {r for r, _ in ROLES}


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


def _clean(form):
    return {k: request.form.get(k, '').strip() for k in
            ('full_name', 'username', 'email', 'phone', 'role')}


def _validate(form, password, user=None, require_password=True):
    errors = []
    if not form['full_name']:
        errors.append('Full name is required.')
    if user is None:
        if not USERNAME_RE.match(form['username']):
            errors.append('Username must be 3-80 characters (letters, numbers, . _ -).')
        elif User.query.filter(func.lower(User.username) == form['username'].lower()).first():
            errors.append('This username is already taken.')
    if not EMAIL_RE.match(form['email']):
        errors.append('Enter a valid email address.')
    else:
        q = User.query.filter(func.lower(User.email) == form['email'].lower())
        if user is not None:
            q = q.filter(User.id != user.id)
        if q.first():
            errors.append('This email is already used by another account.')
    if form['role'] not in VALID_ROLES:
        errors.append('Select a valid role.')
    if (require_password or password) and len(password) < MIN_PASSWORD:
        errors.append(f'Password must be at least {MIN_PASSWORD} characters.')
    return errors


@admin_bp.route('/')
@login_required
@admin_required
def index():
    users = User.query.order_by(User.role, User.full_name).all()
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(50).all()
    return render_template('admin/index.html', users=users, logs=logs)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    form = {}
    if request.method == 'POST':
        form = _clean(request.form)
        password = request.form.get('password', '')
        errors = _validate(form, password)
        if not errors:
            try:
                user = User(username=form['username'], email=form['email'].lower(),
                            full_name=form['full_name'], role=form['role'],
                            phone=form['phone'] or None)
                user.set_password(password)
                db.session.add(user)
                db.session.flush()
                if user.role == 'doctor':
                    # a doctor needs a profile to appear in appointments
                    db.session.add(Doctor(user_id=user.id))
                db.session.add(AuditLog(user_id=current_user.id, action='CREATE_USER', entity='User',
                                        entity_id=user.id, details=f'Created user {user.username} ({user.role})',
                                        ip_address=request.remote_addr))
                db.session.commit()
                flash(f'User {user.username} created successfully.', 'success')
                if user.role == 'doctor':
                    flash('Complete the doctor profile (department, specialization, fee) under '
                          'Setup > Doctors > Edit.', 'info')
                return redirect(url_for('admin.index'))
            except IntegrityError:
                db.session.rollback()
                errors.append('Username or email already exists.')
        for err in errors:
            flash(err, 'danger')
    return render_template('admin/create_user.html', form=form, roles=ROLES)


@admin_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        form = _clean(request.form)
        form['username'] = user.username
        password = request.form.get('password', '')
        if user.id == current_user.id:
            form['role'] = user.role  # cannot demote yourself
        errors = _validate(form, password, user=user, require_password=False)
        if not errors:
            try:
                user.full_name = form['full_name']
                user.email = form['email'].lower()
                user.phone = form['phone'] or None
                user.role = form['role']
                if password:
                    user.set_password(password)
                db.session.add(AuditLog(user_id=current_user.id, action='UPDATE_USER', entity='User',
                                        entity_id=user.id, details=f'Updated user {user.username}'
                                        + (' (password reset)' if password else ''),
                                        ip_address=request.remote_addr))
                db.session.commit()
                flash('User updated successfully.', 'success')
                return redirect(url_for('admin.index'))
            except IntegrityError:
                db.session.rollback()
                errors.append('Email already exists.')
        for err in errors:
            flash(err, 'danger')
    return render_template('admin/edit_user.html', user=user, roles=ROLES)


@admin_bp.route('/users/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Cannot deactivate yourself.', 'warning')
    else:
        user.is_active = not user.is_active
        db.session.add(AuditLog(user_id=current_user.id, action='TOGGLE_USER', entity='User',
                                entity_id=user.id,
                                details=f'{user.username} {"activated" if user.is_active else "deactivated"}',
                                ip_address=request.remote_addr))
        db.session.commit()
        flash(f'User {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.index'))
