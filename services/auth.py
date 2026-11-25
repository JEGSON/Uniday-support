"""Authentication helpers for Flask-Login."""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from flask_login import UserMixin
from pymongo import ReturnDocument

import db
from services.passwords import hash_password, needs_rehash, rehash_verified_password, verify_password
from services import audit

_DUMMY_HASH = hash_password('a unique dummy password for timing')


class User(UserMixin):
    def __init__(self, document):
        self.id = str(document['_id'])
        self.role = document['role']
        self.previous_login_at = document.get('last_login_at')


def load_user(user_id):
    if not isinstance(user_id, str) or not ObjectId.is_valid(user_id):
        return None
    document = db.get_users().find_one({'_id': ObjectId(user_id), 'is_active': True})
    return User(document) if document else None


def authenticate(identifier, password):
    if not isinstance(identifier, str) or len(identifier) > 254 or not isinstance(password, str):
        return None
    identifier = identifier.strip()
    users = db.get_users()
    lookup = {'email': identifier.lower()} if '@' in identifier else {'$or': [
        {'student_id': identifier.upper()}, {'staff_id': identifier.upper()}]}
    user = users.find_one(lookup)
    now = datetime.now(timezone.utc)
    eligible = bool(user and user.get('is_active') is True and user.get('password_hash')
                    and (not user.get('locked_until') or user['locked_until'] <= now))
    valid = verify_password(user['password_hash'] if eligible else _DUMMY_HASH, password)
    if not eligible:
        return None
    if not valid:
        updated = users.find_one_and_update({'_id': user['_id'], 'is_active': True},
                                             {'$inc': {'failed_login_count': 1}},
                                             return_document=ReturnDocument.AFTER)
        if updated and updated.get('failed_login_count', 0) >= 5:
            users.update_one({'_id': user['_id'], 'failed_login_count': {'$gte': 5}},
                             {'$set': {'locked_until': now + timedelta(minutes=5), 'failed_login_count': 0}})
            audit.record('account_lockout', user['_id'])
        return None
    update = {'last_login_at': now, 'failed_login_count': 0, 'locked_until': None}
    if needs_rehash(user['password_hash']):
        update['password_hash'] = rehash_verified_password(password)
    users.update_one({'_id': user['_id'], 'is_active': True}, {'$set': update})
    return User(user)
