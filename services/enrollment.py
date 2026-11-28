"""Registry-backed account enrollment and email confirmation."""
from datetime import datetime, timedelta, timezone
import hmac
import smtplib

from bson import ObjectId
from flask import current_app
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import db
from services import audit, mail, tokens
from services.passwords import hash_password


def register(values):
    """Reserve a trusted record, create an inactive account and send a link."""
    registry = db.get_registry()
    users = db.get_users()
    now = datetime.now(timezone.utc)
    user_id = ObjectId()
    # Only validated strings reach this query; one winner can claim a record.
    matched = registry.find_one_and_update(
        {'student_id': values['student_id'], 'university_email': values['email'], 'claimed': False},
        {'$set': {'claimed': True, 'claimed_at': now, 'claimed_by_user_id': user_id}},
        return_document=ReturnDocument.AFTER,
    )
    if matched is None:
        audit.record('registry_match_failure')
        return
    audit.record('registry_claim', user_id)
    document = {'_id': user_id, 'student_id': matched['student_id'], 'email': matched['university_email'],
                'full_name': matched['full_name'], 'course': matched['course'], 'role': 'student',
                'password_hash': None, 'is_active': False, 'email_verified': False,
                'student_identity_verified': True, 'failed_login_count': 0, 'locked_until': None,
                'created_at': now, 'last_login_at': None, 'password_changed_at': None}
    try:
        users.insert_one(document)
    except Exception:
        # Compensate on an ordinary insert failure; a process crash needs manual
        # reconciliation because a standalone MongoDB has no transactions.
        registry.update_one({'_id': matched['_id'], 'claimed_by_user_id': user_id},
                            {'$set': {'claimed': False, 'claimed_at': None, 'claimed_by_user_id': None}})
        raise
    issue_email(user_id)


def issue_email(user_id):
    """Atomically replace the current token and enforce the per-account cooldown."""
    users = db.get_users()
    now = datetime.now(timezone.utc)
    raw = tokens.generate_token()
    record = tokens.new_token_record(user_id, raw, now)
    user = users.find_one_and_update(
        {'_id': user_id, 'is_active': False, 'role': 'student', 'student_identity_verified': True,
         '$or': [{'verification_sent_at': {'$exists': False}},
                 {'verification_sent_at': {'$lte': now - timedelta(minutes=1)}}]},
        {'$set': {'verification_hash': record['token_hash'], 'verification_expires_at': record['expires_at'],
                  'verification_sent_at': now}}, return_document=ReturnDocument.AFTER,
    )
    if user is None:
        audit.record('resend_rate_limited', user_id)
        return
    # Records are informational/TTL cleanup; the current hash on the user is
    # the authoritative single-use guard, even if a process crashes mid-update.
    collection = db.get_db('MONGODB_AUTH_DB').verification_tokens
    tokens.ensure_indexes(collection)
    collection.update_many({'user_id': user_id, 'used_at': None}, {'$set': {'used_at': now}})
    collection.insert_one(record)
    try:
        mail.send_verification_email(user['email'], raw, current_app.config['BASE_URL'],
                                     smtp_host=current_app.config['SMTP_HOST'])
        audit.record('verification_email_sent', user_id)
    except (OSError, smtplib.SMTPException, ValueError):
        current_app.logger.warning('Verification email could not be delivered.')


def resend(email):
    user = db.get_users().find_one({'email': email, 'role': 'student', 'is_active': False,
                                    'student_identity_verified': True}, {'_id': 1})
    audit.record('resend_requested', user['_id'] if user else None)
    if user:
        issue_email(user['_id'])


def confirm(token, password):
    try:
        digest = tokens.token_hash(token)
    except ValueError:
        audit.record('verification_failure')
        return False
    users = db.get_users()
    user = users.find_one({'verification_hash': digest, 'is_active': False, 'role': 'student',
                           'student_identity_verified': True})
    now = datetime.now(timezone.utc)
    if not user or not hmac.compare_digest(user['verification_hash'], digest):
        audit.record('verification_failure')
        return False
    if user.get('verification_expires_at') is None or user['verification_expires_at'] <= now:
        audit.record('token_expired', user['_id'])
        return False
    # Password is chosen after opening the mailbox link. An attacker who only
    # knows registry details cannot set the final account password.
    password_hash = hash_password(password)
    result = users.update_one({'_id': user['_id'], 'is_active': False, 'student_identity_verified': True,
                               'verification_hash': digest,
                               'verification_expires_at': {'$gt': now}},
                              {'$set': {'password_hash': password_hash, 'is_active': True,
                                        'email_verified': True, 'password_changed_at': now},
                               '$unset': {'verification_hash': '', 'verification_expires_at': ''}})
    if not result.modified_count:
        audit.record('verification_failure')
        return False
    try:
        db.get_db('MONGODB_AUTH_DB').verification_tokens.update_many(
            {'user_id': user['_id'], 'used_at': None}, {'$set': {'used_at': now}})
    except Exception:
        # The user-document guard has already made the token unusable.
        current_app.logger.warning('Verification token bookkeeping could not be updated.')
    audit.record('verification_success', user['_id'])
    return True
