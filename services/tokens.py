"""Primitives for short-lived, single-use email verification tokens."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets

_TOKEN = re.compile(r'[A-Za-z0-9_-]{43}\Z', re.ASCII)


def generate_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise ValueError('Invalid token.')
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def token_matches(token, record, now=None):
    """Validate explicitly; MongoDB TTL removal is asynchronous cleanup only."""
    try:
        candidate = token_hash(token)
        stored = record['token_hash']
        expiry = record['expires_at']
        now = now or datetime.now(timezone.utc)
        if not isinstance(stored, str) or not isinstance(expiry, datetime):
            return False
        if expiry.tzinfo is None or now.tzinfo is None:
            return False
        return (record.get('purpose') == 'verify_email' and record.get('used_at') is None
                and expiry > now and hmac.compare_digest(candidate, stored))
    except (KeyError, TypeError, ValueError):
        return False


def new_token_record(user_id, token, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Token timestamps must be timezone-aware.')
    return {'user_id': user_id, 'token_hash': token_hash(token), 'purpose': 'verify_email',
            'created_at': now, 'expires_at': now + timedelta(minutes=30), 'used_at': None}


def ensure_indexes(collection):
    collection.create_index('token_hash', unique=True, name='unique_verification_token')
    collection.create_index('expires_at', expireAfterSeconds=0, name='expire_verification_token')
