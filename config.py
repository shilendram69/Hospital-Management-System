import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


def _database_url():
    """Read the PostgreSQL URL from DATA_BASE_URL (.env). No SQLite fallback."""
    url = (os.environ.get('DATA_BASE_URL') or os.environ.get('DATABASE_URL') or '').strip()
    if not url:
        raise RuntimeError(
            "DATA_BASE_URL is not set. Create a .env file in the project root with:\n"
            "DATA_BASE_URL=postgresql://user:password@host/dbname?sslmode=require"
        )
    # Heroku/Neon style aliases -> SQLAlchemy dialect name
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if not url.startswith('postgresql'):
        raise RuntimeError("DATA_BASE_URL must be a PostgreSQL URL (postgresql://...).")
    # be explicit about the driver (psycopg2) when none is given
    if url.startswith('postgresql://'):
        url = 'postgresql+psycopg2://' + url[len('postgresql://'):]
    return url


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-only-change-me'
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Neon's pooler may close idle connections -> validate before use & recycle often
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
        'pool_size': 5,
        'max_overflow': 5,
        'connect_args': {'connect_timeout': 20},
    }

    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    WTF_CSRF_TIME_LIMIT = None  # token valid for the whole session

    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ITEMS_PER_PAGE = 20

    HOSPITAL_NAME = os.environ.get('HOSPITAL_NAME', "City Care Multi-Specialty Hospital")
    HOSPITAL_ADDRESS = os.environ.get('HOSPITAL_ADDRESS', "123 Healthcare Avenue, Medical District")
    HOSPITAL_PHONE = os.environ.get('HOSPITAL_PHONE', "+91-1800-123-4567")
    HOSPITAL_EMAIL = os.environ.get('HOSPITAL_EMAIL', "info@citycarehospital.com")
