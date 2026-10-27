from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Attendance, AuditLog, Staff
from app.utils.decorators import roles_required

staff_bp = Blueprint('staff', __name__)

ATTENDANCE_STATUSES = ('Present', 'Absent', 'Leave', 'Half-day')


@staff_bp.route('/')
@login_required
def list_staff():
    staff_list = Staff.query.filter_by(is_active=True).all()
    return render_template('staff/list.html', staff_list=staff_list)


@staff_bp.route('/attendance')
@login_required
def attendance():
    today = date.today()
    records = Attendance.query.filter_by(date=today).all()
    staff_options = Staff.query.filter_by(is_active=True).all() if current_user.role == 'admin' else []
    return render_template('staff/attendance.html', records=records, today=today,
                           staff_options=staff_options, statuses=ATTENDANCE_STATUSES)


@staff_bp.route('/attendance/mark', methods=['POST'])
@login_required
@roles_required()  # admin only
def mark_attendance():
    staff = db.session.get(Staff, request.form.get('staff_id', type=int) or 0)
    action = request.form.get('action', 'check_in')
    status = request.form.get('status', 'Present')
    if not staff:
        flash('Select a staff member.', 'danger')
        return redirect(url_for('staff.attendance'))
    if status not in ATTENDANCE_STATUSES:
        status = 'Present'
    today = date.today()
    rec = Attendance.query.filter_by(staff_id=staff.id, date=today).first()
    now = datetime.now()
    if action == 'check_out':
        if not rec or not rec.check_in:
            flash('This staff member has not checked in today.', 'warning')
            return redirect(url_for('staff.attendance'))
        rec.check_out = now
        flash('Check-out recorded.', 'success')
    else:
        if not rec:
            rec = Attendance(staff_id=staff.id, date=today)
            db.session.add(rec)
        rec.status = status
        if status in ('Present', 'Half-day') and not rec.check_in:
            rec.check_in = now
        flash('Attendance recorded.', 'success')
    db.session.add(AuditLog(user_id=current_user.id, action='MARK_ATTENDANCE', entity='Attendance',
                            details=f'{action} for staff {staff.employee_id}', ip_address=request.remote_addr))
    db.session.commit()
    return redirect(url_for('staff.attendance'))
