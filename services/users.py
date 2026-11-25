"""Validation and creation of student accounts."""

import re
import unicodedata
from datetime import datetime, timezone

from email_validator import EmailNotValidError, validate_email
from pymongo.errors import DuplicateKeyError

import db
from services.passwords import hash_password, validate_password

_STUDENT_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z', re.ASCII)


def validate_signup(data):
    """Return sanitized non-secret values and field errors; never trust input types."""
    values, errors = {}, {}
    for key, label, maximum in (('full_name', 'your name', 120), ('student_id', 'your student ID', 64),
                                ('email', 'your university email address', 254), ('course', 'your course', 160)):
        raw = data.get(key)
        if not isinstance(raw, str):
            values[key] = ''
            errors[key] = f'Enter {label}.'
            continue
        value = unicodedata.normalize('NFC', raw.strip())
        values[key] = value
        if not value or len(value) > maximum or any(unicodedata.category(c).startswith('C') for c in value):
            errors[key] = f'Enter {label} using no more than {maximum} characters.'

    if 'student_id' not in errors:
        if not _STUDENT_ID.fullmatch(values['student_id']):
            errors['student_id'] = 'Use letters, numbers, underscores or hyphens for your student ID.'
        else:
            values['student_id'] = values['student_id'].upper()

    if 'email' not in errors:
        try:
            # Syntax validation is offline; email ownership is not established.
            email = validate_email(values['email'], check_deliverability=False, allow_smtputf8=False).normalized.lower()
            if len(email) > 254:
                raise EmailNotValidError('Email is too long')
            values['email'] = email
        except EmailNotValidError:
            errors['email'] = 'Enter a valid university email address.'

    password = data.get('password')
    password_error = validate_password(password)
    if password_error:
        errors['password'] = password_error
    confirmation = data.get('confirm_password')
    if not isinstance(confirmation, str) or not confirmation or confirmation != password:
        errors['confirm_password'] = 'Those passwords do not match yet.'
    return values, errors


def create_student(values, password):
    """Insert only explicitly selected fields; public requests cannot assign roles."""
    now = datetime.now(timezone.utc)
    document = {
        'student_id': values['student_id'], 'full_name': values['full_name'],
        'email': values['email'], 'course': values['course'],
        # Fail closed: neither an email address nor a student ID proves ownership.
        'password_hash': hash_password(password), 'role': 'student', 'is_active': False,
        'email_verified': False, 'student_identity_verified': False,
        'failed_login_count': 0, 'locked_until': None, 'created_at': now,
        'last_login_at': None, 'password_changed_at': now,
    }
    try:
        db.get_users().insert_one(document)
    except DuplicateKeyError:
        # The route returns the same generic response for either unique index.
        pass


def create_privileged_user(data, role, activate=False):
    """Provision a staff or admin account for a trusted local operator."""
    if role not in ('staff', 'admin') or not isinstance(activate, bool):
        raise ValueError('Invalid privileged account options.')
    # Reuse the same normalization and type checks; no student fields are stored.
    signup_data = {'full_name': data.get('full_name'), 'student_id': data.get('staff_id'),
                   'email': data.get('email'), 'course': 'Not applicable',
                   'password': data.get('password'), 'confirm_password': data.get('confirm_password')}
    values, errors = validate_signup(signup_data)
    if errors:
        # These are fixed validation messages, never user-supplied values.
        messages = [message.replace('student ID', 'staff ID') for message in errors.values()]
        raise ValueError(' '.join(messages))
    now = datetime.now(timezone.utc)
    document = {
        'staff_id': values['student_id'], 'full_name': values['full_name'], 'email': values['email'],
        'password_hash': hash_password(signup_data['password']), 'role': role, 'is_active': activate,
        'email_verified': False, 'identity_verified': False,
        'failed_login_count': 0, 'locked_until': None, 'created_at': now,
        'last_login_at': None, 'password_changed_at': now,
    }
    db.get_users().insert_one(document)
