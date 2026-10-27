import re
from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import AuditLog, User

auth_bp = Blueprint('auth', __name__)

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,80}$')
MIN_PASSWORD = 8


def _safe_next(target):
    """Only allow relative redirects after login."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme or not target.startswith('/'):
        return None
    return target


# ------------------------------------------------------------------ FIRST-TIME SETUP
@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """Create the very first administrator. Disabled forever once any user exists."""
    if db.session.query(User.id).first() is not None:
        current_app.config['_SETUP_COMPLETE'] = True
        flash('Setup is already complete. Please sign in.', 'info')
        return redirect(url_for('auth.login'))

    form = {}
    if request.method == 'POST':
        form = {k: request.form.get(k, '').strip() for k in
                ('full_name', 'username', 'email', 'phone')}
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        errors = []
        if not form['full_name']:
            errors.append('Full name is required.')
        if not USERNAME_RE.match(form['username']):
            errors.append('Username must be 3-80 characters (letters, numbers, . _ -).')
        if not EMAIL_RE.match(form['email']):
            errors.append('Enter a valid email address.')
        if len(password) < MIN_PASSWORD:
            errors.append(f'Password must be at least {MIN_PASSWORD} characters.')
        if password != confirm:
            errors.append('Password and confirm password do not match.')

        if not errors:
            try:
                if db.engine.dialect.name == 'postgresql':
                    # serialise two people submitting setup at the same moment
                    db.session.execute(text('SELECT pg_advisory_xact_lock(7272702)'))
                if db.session.query(User.id).first() is not None:
                    db.session.rollback()
                    flash('Setup was already completed by someone else.', 'info')
                    return redirect(url_for('auth.login'))

                admin = User(username=form['username'], email=form['email'].lower(),
                             full_name=form['full_name'], role='admin',
                             phone=form['phone'] or None)
                admin.set_password(password)
                db.session.add(admin)
                db.session.flush()
                db.session.add(AuditLog(user_id=admin.id, action='SETUP_ADMIN', entity='User',
                                        entity_id=admin.id,
                                        details='First administrator account created',
                                        ip_address=request.remote_addr))
                admin.last_login = datetime.utcnow()
                db.session.commit()
                current_app.config['_SETUP_COMPLETE'] = True
                login_user(admin)
                flash('Administrator account created. Start by adding departments, doctors and beds '
                      'from the Setup hub.', 'success')
                return redirect(url_for('manage.hub'))
            except IntegrityError:
                db.session.rollback()
                errors.append('Could not create the account. Please try again.')
        for err in errors:
            flash(err, 'danger')

    return render_template('auth/setup.html', form=form)


# ------------------------------------------------------------------ LOGIN / LOGOUT
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.add(AuditLog(user_id=user.id, action='LOGIN',
                                    details=f'User {user.username} logged in',
                                    ip_address=request.remote_addr))
            db.session.commit()
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(_safe_next(request.args.get('next')) or url_for('main.dashboard'))
        flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    db.session.add(AuditLog(user_id=current_user.id, action='LOGOUT',
                            details=f'User {current_user.username} logged out',
                            ip_address=request.remote_addr))
    db.session.commit()
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


# ------------------------------------------------------------------ PROFILE
@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html')


@auth_bp.route('/profile/password', methods=['POST'])
@login_required
def change_password():
    current = request.form.get('current_password', '')
    new = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    if not current_user.check_password(current):
        flash('Current password is incorrect.', 'danger')
    elif len(new) < MIN_PASSWORD:
        flash(f'New password must be at least {MIN_PASSWORD} characters.', 'danger')
    elif new != confirm:
        flash('New password and confirmation do not match.', 'danger')
    else:
        current_user.set_password(new)
        db.session.add(AuditLog(user_id=current_user.id, action='CHANGE_PASSWORD',
                                entity='User', entity_id=current_user.id,
                                ip_address=request.remote_addr))
        db.session.commit()
        flash('Password changed successfully.', 'success')
    return redirect(url_for('auth.profile'))
