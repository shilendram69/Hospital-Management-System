import logging
import os

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.login_message = 'Please log in to access this page.'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ---------------- Blueprints ----------------
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp
    from app.blueprints.patients import patients_bp
    from app.blueprints.appointments import appointments_bp
    from app.blueprints.doctors import doctors_bp
    from app.blueprints.billing import billing_bp
    from app.blueprints.records import records_bp
    from app.blueprints.adt import adt_bp
    from app.blueprints.pharmacy import pharmacy_bp
    from app.blueprints.lab import lab_bp
    from app.blueprints.staff import staff_bp
    from app.blueprints.inventory import inventory_bp
    from app.blueprints.reports import reports_bp
    from app.blueprints.portal import portal_bp
    from app.blueprints.emergency import emergency_bp
    from app.blueprints.nursing import nursing_bp
    from app.blueprints.radiology import radiology_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.masters import manage_bp, shortcuts_for

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(patients_bp, url_prefix='/patients')
    app.register_blueprint(appointments_bp, url_prefix='/appointments')
    app.register_blueprint(doctors_bp, url_prefix='/doctors')
    app.register_blueprint(billing_bp, url_prefix='/billing')
    app.register_blueprint(records_bp, url_prefix='/records')
    app.register_blueprint(adt_bp, url_prefix='/adt')
    app.register_blueprint(pharmacy_bp, url_prefix='/pharmacy')
    app.register_blueprint(lab_bp, url_prefix='/lab')
    app.register_blueprint(staff_bp, url_prefix='/staff')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(portal_bp, url_prefix='/portal')
    app.register_blueprint(emergency_bp, url_prefix='/emergency')
    app.register_blueprint(nursing_bp, url_prefix='/nursing')
    app.register_blueprint(radiology_bp, url_prefix='/radiology')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(manage_bp, url_prefix='/manage')

    # ---------------- Database: create missing tables (no data is inserted) ----------------
    from app.utils.db_init import init_database
    init_database(app)

    # ---------------- Request hooks ----------------
    @app.before_request
    def enforce_first_time_setup():
        """Until the first admin exists, the ONLY thing that works is /setup."""
        if app.config.get('_SETUP_COMPLETE'):
            return None
        if request.endpoint in (None, 'static', 'auth.setup'):
            return None
        if db.session.query(User.id).first() is not None:
            app.config['_SETUP_COMPLETE'] = True
            return None
        return redirect(url_for('auth.setup'))

    @app.before_request
    def block_deactivated_users():
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash('Your account has been deactivated. Contact the administrator.', 'danger')
            return redirect(url_for('auth.login'))
        return None

    @app.context_processor
    def inject_globals():
        return {
            'hospital_name': app.config['HOSPITAL_NAME'],
            'manage_shortcuts': shortcuts_for(request.endpoint) if current_user.is_authenticated else [],
        }

    # ---------------- Error handlers ----------------
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash('Your session expired or the form was invalid. Please try again.', 'warning')
        return redirect(request.referrer or url_for('main.index'))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/error.html', code=403, title='Access denied',
                               message='You do not have permission to open this page.'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/error.html', code=404, title='Page not found',
                               message='The page you are looking for does not exist.'), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template('errors/error.html', code=500, title='Something went wrong',
                               message='An unexpected error occurred. Please try again.'), 500

    return app
