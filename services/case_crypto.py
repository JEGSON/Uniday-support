"""Authenticated case-field encryption. Keys remain in application configuration."""
import json
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


class CaseEncryptionError(RuntimeError):
    """Encryption is unavailable or stored ciphertext failed verification."""


def _key(key_id):
    try:
        keys = json.loads(current_app.config.get('CASE_ENCRYPTION_KEYS') or '{}')
        if not isinstance(keys, dict) or not isinstance(key_id, str) or key_id not in keys:
            raise ValueError('Unknown key identifier')
        return Fernet(keys[key_id].encode('ascii'))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CaseEncryptionError('Case encryption is unavailable.') from None


def encrypt_text(text, reference, field):
    if not all(isinstance(item, str) and item for item in (text, reference, field)):
        raise CaseEncryptionError('Case encryption is unavailable.')
    key_id = current_app.config.get('CASE_ACTIVE_KEY_ID')
    payload = json.dumps({'text': text, 'reference': reference, 'field': field}, ensure_ascii=False).encode('utf-8')
    token = _key(key_id).encrypt(payload).decode('ascii')
    return {'key_id': key_id, 'ciphertext': token}


def decrypt_text(envelope, reference, field):
    try:
        if not isinstance(envelope, dict) or set(envelope) != {'key_id', 'ciphertext'}:
            raise ValueError('Unexpected envelope')
        token = envelope['ciphertext']
        if not isinstance(token, str):
            raise ValueError('Invalid ciphertext')
        payload = json.loads(_key(envelope['key_id']).decrypt(token.encode('ascii')).decode('utf-8'))
        if not isinstance(payload, dict) or payload.get('reference') != reference or payload.get('field') != field or not isinstance(payload.get('text'), str):
            raise ValueError('Wrong context')
        return payload['text']
    except (InvalidToken, ValueError, TypeError, UnicodeError, AttributeError):
        raise CaseEncryptionError('Case content could not be decrypted.') from None
