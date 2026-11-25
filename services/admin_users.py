"""Conservative local account management with conditional updates."""
from bson import ObjectId
from pymongo import ReturnDocument
import db

ROLES = ('student', 'staff', 'admin')


def _admin(user):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'role', None) != 'admin':
        raise PermissionError('Administrator access required.')
    if not isinstance(user.id, str) or not ObjectId.is_valid(user.id):
        raise ValueError('Invalid administrator ID.')
    return ObjectId(user.id)


def list_users(user):
    _admin(user)
    # Projection excludes all password hashes, tokens and account recovery fields.
    docs = db.get_users().find({}, {'full_name': 1, 'role': 1, 'is_active': 1}).sort('_id', 1).limit(100)
    return [{'reference': str(doc['_id']), 'name': doc.get('full_name', 'Unnamed account'),
             'role': doc.get('role', ''), 'active': doc.get('is_active') is True} for doc in docs]


def change_user(user, target, action, value):
    actor = _admin(user)
    if not isinstance(target, str) or not ObjectId.is_valid(target) or not isinstance(action, str) or not isinstance(value, str):
        raise ValueError('Invalid account action.')
    target_id = ObjectId(target)
    if target_id == actor:
        raise PermissionError('You cannot change your own account here.')
    # Protect every admin account. This conservative standalone-MongoDB rule
    # avoids the last-admin race without pretending that count-then-write is atomic.
    allowed = {'_id': target_id, 'role': {'$in': ['student', 'staff']}}
    if action == 'status' and value in ('activate', 'deactivate'):
        active = value == 'activate'
        allowed['is_active'] = not active
        if active:
            # Activation cannot bypass registry/email or operator identity checks.
            allowed['password_hash'] = {'$type': 'string'}
            allowed['$or'] = [{'role': 'student', 'email_verified': True, 'student_identity_verified': True},
                              {'role': 'staff', 'identity_verified': True}]
        update = {'$set': {'is_active': active}}
        event = 'user_activated' if active else 'user_deactivated'
    elif action == 'role' and value in ROLES:
        # Granting privileged roles is deliberately reserved for the secure CLI.
        if value in ('staff', 'admin'):
            raise PermissionError('Privileged accounts are managed with the secure CLI.')
        allowed['role'] = {'$in': ['student', 'staff'], '$ne': value}
        if value == 'student':
            allowed.update(email_verified=True, student_identity_verified=True)
        update = {'$set': {'role': value}}
        event = 'role_changed'
    else:
        raise ValueError('Invalid account action.')
    previous = db.get_users().find_one_and_update(allowed, update, projection={'role': 1}, return_document=ReturnDocument.BEFORE)
    if previous is None:
        raise PermissionError('This account cannot be changed by this action.')
    return event, target_id, previous.get('role'), value if action == 'role' else None
