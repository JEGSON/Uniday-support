"""Server-side authorization for role-restricted views."""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from services import audit


def role_required(*roles):
    """Require authentication and an explicitly allowed server-side role."""
    if not roles or any(role not in ('student', 'staff', 'admin') for role in roles):
        raise ValueError('At least one recognised role is required.')

    def decorate(view):
        @wraps(view)
        @login_required
        def checked(*args, **kwargs):
            if getattr(current_user, 'role', None) not in roles:
                audit.record('role_denial', current_user.id)
                abort(403)
            return view(*args, **kwargs)
        return checked
    return decorate
