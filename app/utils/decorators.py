from functools import wraps
from flask import abort
from flask_login import current_user


def roles_required(*roles):
    """Allow admins and any of the given roles."""
    def wrapper(fn):
        @wraps(fn)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_user_unauthorized()
            if current_user.role != 'admin' and current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return decorated
    return wrapper


def current_user_unauthorized():
    from app import login_manager
    return login_manager.unauthorized()
