from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models import (
    Patient, Appointment, Admission, Bill, Medicine, LabOrder,
    Bed, EmergencyVisit, Doctor, Department
)
from datetime import date, datetime, timedelta
from sqlalchemy import func

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect_to_dashboard()
    return render_template('index.html')


def redirect_to_dashboard():
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    
    # Core KPIs
    total_patients = Patient.query.filter_by(is_active=True).count()
    today_appointments = Appointment.query.filter(
        Appointment.appointment_date == today,
        Appointment.status.in_(['Scheduled', 'Confirmed', 'In Progress'])
    ).count()
    admitted_patients = Admission.query.filter_by(status='Admitted').count()
    available_beds = Bed.query.filter_by(status='Available').count()
    total_beds = Bed.query.count()
    occupancy = round((total_beds - available_beds) / total_beds * 100, 1) if total_beds else 0
    
    pending_bills = Bill.query.filter(Bill.payment_status.in_(['Pending', 'Partial']), Bill.is_cancelled == False).count()
    low_stock_meds = Medicine.query.filter(Medicine.current_stock <= Medicine.reorder_level, Medicine.is_active == True).count()
    pending_labs = LabOrder.query.filter(LabOrder.status.in_(['Ordered', 'Sample Collected', 'In Progress'])).count()
    emergency_waiting = EmergencyVisit.query.filter_by(status='Waiting').count()
    
    # Today's appointments list
    todays_appts = Appointment.query.filter(
        Appointment.appointment_date == today
    ).order_by(Appointment.appointment_time).limit(10).all()
    
    # Recent patients
    recent_patients = Patient.query.order_by(Patient.registration_date.desc()).limit(5).all()
    
    # Revenue today
    today_revenue = db.session.query(func.coalesce(func.sum(Bill.paid_amount), 0)).filter(
        func.date(Bill.bill_date) == today
    ).scalar()
    
    stats = {
        'total_patients': total_patients,
        'today_appointments': today_appointments,
        'admitted_patients': admitted_patients,
        'available_beds': available_beds,
        'total_beds': total_beds,
        'occupancy': occupancy,
        'pending_bills': pending_bills,
        'low_stock_meds': low_stock_meds,
        'pending_labs': pending_labs,
        'emergency_waiting': emergency_waiting,
        'today_revenue': today_revenue or 0,
    }
    
    setup_pending = []
    if current_user.role == 'admin':
        from app.blueprints.masters import get_setup_steps
        setup_pending = [st for st in get_setup_steps() if not st['done']]

    return render_template('dashboard.html', stats=stats, todays_appts=todays_appts,
                           recent_patients=recent_patients, today=today, setup_pending=setup_pending)


# Import db for the revenue query
from app import db
