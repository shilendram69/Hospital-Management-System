from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

# ==================== USER & ROLE ====================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='receptionist')  # admin, doctor, nurse, receptionist, pharmacist, lab_tech, radiologist
    is_active = db.Column(db.Boolean, default=True)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    doctor_profile = db.relationship('Doctor', backref='user', uselist=False)
    staff_profile = db.relationship('Staff', backref='user', uselist=False)
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, *roles):
        return self.role in roles

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(100), nullable=False)
    entity = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ==================== DEPARTMENT & DOCTOR ====================
class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    head_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id', use_alter=True, name='fk_departments_head_doctor'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    doctors = db.relationship('Doctor', backref='department', lazy='dynamic', foreign_keys='Doctor.department_id')
    wards = db.relationship('Ward', backref='department', lazy='dynamic')

    def __repr__(self):
        return f'<Department {self.name}>'


class Doctor(db.Model):
    __tablename__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    specialization = db.Column(db.String(100))
    qualification = db.Column(db.String(200))
    experience_years = db.Column(db.Integer, default=0)
    consultation_fee = db.Column(db.Float, default=500.0)
    license_number = db.Column(db.String(50), unique=True)
    availability = db.Column(db.String(200))  # e.g. "Mon-Fri 9AM-5PM"
    is_available = db.Column(db.Boolean, default=True)
    bio = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship('Appointment', backref='doctor', lazy='dynamic')
    medical_records = db.relationship('MedicalRecord', backref='doctor', lazy='dynamic')

    def __repr__(self):
        return f'<Doctor {self.user.full_name if self.user else self.id}>'


# ==================== PATIENT ====================
class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    uhid = db.Column(db.String(20), unique=True, nullable=False, index=True)  # Unique Hospital ID
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10), nullable=False)  # Male, Female, Other
    blood_group = db.Column(db.String(5))
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    state = db.Column(db.String(50))
    pincode = db.Column(db.String(10))
    emergency_contact_name = db.Column(db.String(100))
    emergency_contact_phone = db.Column(db.String(20))
    emergency_contact_relation = db.Column(db.String(50))
    medical_history = db.Column(db.Text)
    allergies = db.Column(db.Text)
    chronic_conditions = db.Column(db.Text)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    photo = db.Column(db.String(200))
    aadhaar = db.Column(db.String(12))  # For ABDM readiness
    insurance_provider = db.Column(db.String(100))
    insurance_policy_number = db.Column(db.String(50))
    insurance_coverage = db.Column(db.Float)

    # Relationships
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic')
    medical_records = db.relationship('MedicalRecord', backref='patient', lazy='dynamic')
    admissions = db.relationship('Admission', backref='patient', lazy='dynamic')
    bills = db.relationship('Bill', backref='patient', lazy='dynamic')
    lab_orders = db.relationship('LabOrder', backref='patient', lazy='dynamic')
    prescriptions = db.relationship('Prescription', backref='patient', lazy='dynamic')
    radiology_orders = db.relationship('RadiologyOrder', backref='patient', lazy='dynamic')
    emergency_visits = db.relationship('EmergencyVisit', backref='patient', lazy='dynamic')

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    def __repr__(self):
        return f'<Patient {self.uhid} - {self.full_name}>'


# ==================== APPOINTMENT ====================
class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    appointment_date = db.Column(db.Date, nullable=False, index=True)
    appointment_time = db.Column(db.String(10), nullable=False)  # HH:MM
    status = db.Column(db.String(20), default='Scheduled')  # Scheduled, Confirmed, In Progress, Completed, Cancelled, No-Show
    appointment_type = db.Column(db.String(30), default='OPD')  # OPD, Follow-up, Emergency, Telemedicine
    reason = db.Column(db.Text)
    notes = db.Column(db.Text)
    is_walk_in = db.Column(db.Boolean, default=False)
    queue_number = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    department = db.relationship('Department')

    def __repr__(self):
        return f'<Appointment {self.id} - {self.patient.full_name if self.patient else ""}>'


# ==================== MEDICAL RECORDS ====================
class MedicalRecord(db.Model):
    __tablename__ = 'medical_records'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False, index=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    visit_date = db.Column(db.DateTime, default=datetime.utcnow)
    chief_complaint = db.Column(db.Text)
    symptoms = db.Column(db.Text)
    examination_findings = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    diagnosis_code = db.Column(db.String(20))  # ICD-10
    treatment_plan = db.Column(db.Text)
    follow_up_date = db.Column(db.Date)
    follow_up_notes = db.Column(db.Text)
    vital_signs = db.Column(db.Text)  # JSON-like string or separate fields
    blood_pressure = db.Column(db.String(20))
    pulse = db.Column(db.Integer)
    temperature = db.Column(db.Float)
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    spo2 = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointment = db.relationship('Appointment')
    prescriptions = db.relationship('Prescription', backref='medical_record', lazy='dynamic')

    def __repr__(self):
        return f'<MedicalRecord {self.id} - Patient {self.patient_id}>'


class Prescription(db.Model):
    __tablename__ = 'prescriptions'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    medical_record_id = db.Column(db.Integer, db.ForeignKey('medical_records.id'))
    prescription_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='Active')  # Active, Dispensed, Cancelled
    is_dispensed = db.Column(db.Boolean, default=False)
    dispensed_at = db.Column(db.DateTime)
    dispensed_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    items = db.relationship('PrescriptionItem', backref='prescription', lazy='dynamic', cascade='all, delete-orphan')
    doctor = db.relationship('Doctor')

    def __repr__(self):
        return f'<Prescription {self.id}>'


class PrescriptionItem(db.Model):
    __tablename__ = 'prescription_items'
    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'))
    medicine_name = db.Column(db.String(150), nullable=False)
    dosage = db.Column(db.String(50))
    frequency = db.Column(db.String(50))  # 1-0-1, TID, etc.
    duration = db.Column(db.String(50))  # 5 days, 1 week
    quantity = db.Column(db.Integer, default=1)
    instructions = db.Column(db.Text)
    route = db.Column(db.String(30), default='Oral')  # Oral, IV, IM, Topical

    medicine = db.relationship('Medicine')


# ==================== ADT (Admission, Discharge, Transfer) ====================
class Ward(db.Model):
    __tablename__ = 'wards'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    ward_type = db.Column(db.String(30))  # General, ICU, Private, Semi-Private, Emergency
    total_beds = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    beds = db.relationship('Bed', backref='ward', lazy='dynamic')

    @property
    def available_beds(self):
        return self.beds.filter_by(status='Available').count()

    def __repr__(self):
        return f'<Ward {self.name}>'


class Bed(db.Model):
    __tablename__ = 'beds'
    id = db.Column(db.Integer, primary_key=True)
    bed_number = db.Column(db.String(20), nullable=False)
    ward_id = db.Column(db.Integer, db.ForeignKey('wards.id'), nullable=False)
    status = db.Column(db.String(20), default='Available')  # Available, Occupied, Maintenance, Reserved
    bed_type = db.Column(db.String(30), default='Standard')  # Standard, ICU, Ventilator
    daily_charge = db.Column(db.Float, default=1500.0)

    current_admission = db.relationship('Admission', backref='bed', uselist=False,
                                        primaryjoin="and_(Bed.id==Admission.bed_id, Admission.status=='Admitted')")

    def __repr__(self):
        return f'<Bed {self.bed_number} ({self.status})>'


class Admission(db.Model):
    __tablename__ = 'admissions'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, index=True)
    bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'))
    admitting_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    admission_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_discharge = db.Column(db.Date)
    actual_discharge = db.Column(db.DateTime)
    admission_type = db.Column(db.String(30), default='Elective')  # Elective, Emergency, Transfer
    status = db.Column(db.String(20), default='Admitted', index=True)  # Admitted, Discharged, Transferred
    reason = db.Column(db.Text)
    diagnosis_on_admission = db.Column(db.Text)
    discharge_summary = db.Column(db.Text)
    discharge_instructions = db.Column(db.Text)
    length_of_stay = db.Column(db.Integer)  # days
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    admitting_doctor = db.relationship('Doctor')
    transfers = db.relationship('Transfer', backref='admission', lazy='dynamic')

    def __repr__(self):
        return f'<Admission {self.id} - Patient {self.patient_id}>'


class Transfer(db.Model):
    __tablename__ = 'transfers'
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('admissions.id'), nullable=False)
    from_bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'))
    to_bed_id = db.Column(db.Integer, db.ForeignKey('beds.id'))
    transfer_date = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.Text)
    transferred_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    from_bed = db.relationship('Bed', foreign_keys=[from_bed_id])
    to_bed = db.relationship('Bed', foreign_keys=[to_bed_id])


# ==================== PHARMACY ====================
class Medicine(db.Model):
    __tablename__ = 'medicines'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    generic_name = db.Column(db.String(150))
    category = db.Column(db.String(50))  # Antibiotic, Analgesic, etc.
    manufacturer = db.Column(db.String(100))
    unit = db.Column(db.String(20), default='Tablet')  # Tablet, Capsule, Syrup, Injection, etc.
    strength = db.Column(db.String(50))
    current_stock = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=50)
    unit_price = db.Column(db.Float, default=0.0)
    selling_price = db.Column(db.Float, default=0.0)
    requires_prescription = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)

    batches = db.relationship('MedicineBatch', backref='medicine', lazy='dynamic')
    stock_movements = db.relationship('StockMovement', backref='medicine', lazy='dynamic')

    @property
    def is_low_stock(self):
        return self.current_stock <= self.reorder_level

    def __repr__(self):
        return f'<Medicine {self.name}>'


class MedicineBatch(db.Model):
    __tablename__ = 'medicine_batches'
    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'), nullable=False)
    batch_number = db.Column(db.String(50), nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, default=0)
    purchase_price = db.Column(db.Float)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    received_date = db.Column(db.Date, default=date.today)
    is_expired = db.Column(db.Boolean, default=False)

    supplier = db.relationship('Supplier')

    def __repr__(self):
        return f'<Batch {self.batch_number}>'


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'
    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicines.id'), nullable=False)
    movement_type = db.Column(db.String(20), nullable=False)  # IN, OUT, ADJUSTMENT, RETURN
    quantity = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(100))  # Bill no, Prescription ID, etc.
    notes = db.Column(db.Text)
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    gstin = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)


# ==================== LABORATORY ====================
class LabTest(db.Model):
    __tablename__ = 'lab_tests'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(20), unique=True)
    category = db.Column(db.String(50))  # Hematology, Biochemistry, Microbiology, etc.
    sample_type = db.Column(db.String(50))  # Blood, Urine, Stool, etc.
    price = db.Column(db.Float, default=0.0)
    normal_range = db.Column(db.String(100))
    unit = db.Column(db.String(30))
    turnaround_hours = db.Column(db.Integer, default=24)
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)


class LabOrder(db.Model):
    __tablename__ = 'lab_orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    ordered_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    priority = db.Column(db.String(20), default='Routine')  # Routine, Urgent, STAT
    status = db.Column(db.String(20), default='Ordered', index=True)  # Ordered, Sample Collected, In Progress, Completed, Cancelled
    clinical_notes = db.Column(db.Text)
    sample_collected_at = db.Column(db.DateTime)
    sample_collected_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    completed_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)

    doctor = db.relationship('Doctor')
    items = db.relationship('LabOrderItem', backref='lab_order', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<LabOrder {self.order_number}>'


class LabOrderItem(db.Model):
    __tablename__ = 'lab_order_items'
    id = db.Column(db.Integer, primary_key=True)
    lab_order_id = db.Column(db.Integer, db.ForeignKey('lab_orders.id'), nullable=False)
    lab_test_id = db.Column(db.Integer, db.ForeignKey('lab_tests.id'), nullable=False)
    status = db.Column(db.String(20), default='Pending')
    result_value = db.Column(db.String(100))
    result_unit = db.Column(db.String(30))
    reference_range = db.Column(db.String(100))
    is_abnormal = db.Column(db.Boolean, default=False)
    remarks = db.Column(db.Text)
    tested_at = db.Column(db.DateTime)
    tested_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    lab_test = db.relationship('LabTest')


# ==================== BILLING ====================
class Bill(db.Model):
    __tablename__ = 'bills'
    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(20), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, index=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('admissions.id'))
    bill_date = db.Column(db.DateTime, default=datetime.utcnow)
    bill_type = db.Column(db.String(30), default='OPD')  # OPD, IPD, Pharmacy, Lab, Package
    subtotal = db.Column(db.Float, default=0.0)
    discount_percent = db.Column(db.Float, default=0.0)
    discount_amount = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    balance_amount = db.Column(db.Float, default=0.0)
    payment_status = db.Column(db.String(20), default='Pending')  # Pending, Partial, Paid, Refunded
    insurance_claim_id = db.Column(db.Integer, db.ForeignKey('insurance_claims.id'))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_cancelled = db.Column(db.Boolean, default=False)

    items = db.relationship('BillItem', backref='bill', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='bill', lazy='dynamic')
    admission = db.relationship('Admission')

    def recalculate(self):
        self.subtotal = sum(item.amount for item in self.items)
        self.discount_amount = self.subtotal * (self.discount_percent / 100)
        self.total_amount = self.subtotal - self.discount_amount + self.tax_amount
        self.balance_amount = self.total_amount - self.paid_amount
        if self.balance_amount <= 0:
            self.payment_status = 'Paid'
        elif self.paid_amount > 0:
            self.payment_status = 'Partial'
        else:
            self.payment_status = 'Pending'


class BillItem(db.Model):
    __tablename__ = 'bill_items'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=False)
    item_type = db.Column(db.String(30))  # Consultation, Lab, Medicine, Procedure, Room, Other
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, default=0.0)
    amount = db.Column(db.Float, default=0.0)
    reference_id = db.Column(db.Integer)  # Link to appointment, lab order, etc.


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bills.id'), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(30))  # Cash, Card, UPI, Insurance, Cheque
    transaction_id = db.Column(db.String(100))
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    is_refund = db.Column(db.Boolean, default=False)


class InsuranceClaim(db.Model):
    __tablename__ = 'insurance_claims'
    id = db.Column(db.Integer, primary_key=True)
    claim_number = db.Column(db.String(30), unique=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    admission_id = db.Column(db.Integer, db.ForeignKey('admissions.id'))
    insurance_provider = db.Column(db.String(100))
    policy_number = db.Column(db.String(50))
    claim_amount = db.Column(db.Float)
    approved_amount = db.Column(db.Float)
    rejected_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default='Submitted')  # Submitted, Under Review, Approved, Rejected, Settled
    pre_auth_number = db.Column(db.String(50))
    submitted_date = db.Column(db.DateTime, default=datetime.utcnow)
    settled_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)

    patient = db.relationship('Patient')
    admission = db.relationship('Admission')
    bills = db.relationship('Bill', backref='insurance_claim')


# ==================== STAFF / HR ====================
class Staff(db.Model):
    __tablename__ = 'staff'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True)
    employee_id = db.Column(db.String(20), unique=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    designation = db.Column(db.String(50))  # Nurse, Technician, Receptionist, Admin, etc.
    joining_date = db.Column(db.Date)
    shift = db.Column(db.String(30))  # Morning, Evening, Night
    salary = db.Column(db.Float)
    is_active = db.Column(db.Boolean, default=True)

    department = db.relationship('Department')
    attendance_records = db.relationship('Attendance', backref='staff', lazy='dynamic')


class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='Present')  # Present, Absent, Leave, Half-day
    notes = db.Column(db.Text)


# ==================== INVENTORY (Equipment & Consumables) ====================
class InventoryItem(db.Model):
    __tablename__ = 'inventory_items'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50))  # Equipment, Consumable, Surgical, Linen
    item_code = db.Column(db.String(30), unique=True)
    unit = db.Column(db.String(20))
    current_stock = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=10)
    unit_cost = db.Column(db.Float, default=0.0)
    location = db.Column(db.String(50))  # Store, Ward, OT
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)

    @property
    def is_low_stock(self):
        return self.current_stock <= self.reorder_level


# ==================== EMERGENCY & TRIAGE ====================
class EmergencyVisit(db.Model):
    __tablename__ = 'emergency_visits'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    arrival_time = db.Column(db.DateTime, default=datetime.utcnow)
    triage_level = db.Column(db.String(20))  # Critical, Urgent, Semi-Urgent, Non-Urgent (ESI 1-5)
    chief_complaint = db.Column(db.Text)
    initial_vitals = db.Column(db.Text)
    triage_notes = db.Column(db.Text)
    triaged_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    status = db.Column(db.String(30), default='Waiting')  # Waiting, Under Treatment, Admitted, Discharged, Transferred
    treatment_started = db.Column(db.DateTime)
    disposition = db.Column(db.String(50))
    disposition_time = db.Column(db.DateTime)

    assigned_doctor = db.relationship('Doctor')


# ==================== NURSING ====================
class NursingNote(db.Model):
    __tablename__ = 'nursing_notes'
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('admissions.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    nurse_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    note_time = db.Column(db.DateTime, default=datetime.utcnow)
    note_type = db.Column(db.String(30))  # Assessment, Progress, Medication, Handover
    content = db.Column(db.Text, nullable=False)
    vitals = db.Column(db.Text)

    nurse = db.relationship('User')
    admission = db.relationship('Admission')
    patient = db.relationship('Patient')


class MedicationAdministration(db.Model):
    __tablename__ = 'medication_administrations'
    id = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey('admissions.id'))
    prescription_item_id = db.Column(db.Integer, db.ForeignKey('prescription_items.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    administered_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    administered_at = db.Column(db.DateTime, default=datetime.utcnow)
    dose_given = db.Column(db.String(50))
    route = db.Column(db.String(30))
    status = db.Column(db.String(20), default='Given')  # Given, Refused, Held, Missed
    notes = db.Column(db.Text)


# ==================== RADIOLOGY ====================
class RadiologyTest(db.Model):
    __tablename__ = 'radiology_tests'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    modality = db.Column(db.String(30))  # X-Ray, CT, MRI, Ultrasound, Mammography
    body_part = db.Column(db.String(50))
    price = db.Column(db.Float, default=0.0)
    duration_minutes = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True)


class RadiologyOrder(db.Model):
    __tablename__ = 'radiology_orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    test_id = db.Column(db.Integer, db.ForeignKey('radiology_tests.id'))
    ordered_date = db.Column(db.DateTime, default=datetime.utcnow)
    scheduled_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='Ordered')  # Ordered, Scheduled, In Progress, Completed, Reported
    clinical_indication = db.Column(db.Text)
    report = db.Column(db.Text)
    reported_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reported_at = db.Column(db.DateTime)
    image_path = db.Column(db.String(200))  # Placeholder for PACS/DICOM integration

    doctor = db.relationship('Doctor')
    test = db.relationship('RadiologyTest')


# ==================== HELPER FUNCTIONS ====================
def generate_uhid():
    """Generate unique hospital ID: HMS-YYYYMMDD-XXXX"""
    today = datetime.now().strftime('%Y%m%d')
    last = Patient.query.filter(Patient.uhid.like(f'HMS-{today}-%')).order_by(Patient.id.desc()).first()
    if last:
        seq = int(last.uhid.split('-')[-1]) + 1
    else:
        seq = 1
    return f'HMS-{today}-{seq:04d}'


def generate_bill_number():
    today = datetime.now().strftime('%Y%m%d')
    last = Bill.query.filter(Bill.bill_number.like(f'BILL-{today}-%')).order_by(Bill.id.desc()).first()
    if last:
        seq = int(last.bill_number.split('-')[-1]) + 1
    else:
        seq = 1
    return f'BILL-{today}-{seq:04d}'


def generate_lab_order_number():
    today = datetime.now().strftime('%Y%m%d')
    last = LabOrder.query.filter(LabOrder.order_number.like(f'LAB-{today}-%')).order_by(LabOrder.id.desc()).first()
    if last:
        seq = int(last.order_number.split('-')[-1]) + 1
    else:
        seq = 1
    return f'LAB-{today}-{seq:04d}'


def generate_radiology_order_number():
    today = datetime.now().strftime('%Y%m%d')
    last = RadiologyOrder.query.filter(RadiologyOrder.order_number.like(f'RAD-{today}-%')).order_by(RadiologyOrder.id.desc()).first()
    if last:
        seq = int(last.order_number.split('-')[-1]) + 1
    else:
        seq = 1
    return f'RAD-{today}-{seq:04d}'
