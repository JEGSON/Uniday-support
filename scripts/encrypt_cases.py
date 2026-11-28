"""Migrate local case text after stopping all application writers.

Default is a read-only dry run. --apply first creates and verifies an encrypted
backup under the ignored data/raw directory, then uses conditional updates.
"""
import argparse
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from bson import BSON
from cryptography.fernet import InvalidToken
from pymongo.errors import PyMongoError

from app import create_app
import db
from services.case_crypto import _key, decrypt_text, encrypt_text, CaseEncryptionError

ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = (ROOT / 'data/raw/case-backups').resolve()
FIELDS = ('student_updates', 'staff_notes')


def transform(document):
    """Validate all known text fields; refuse unknown legacy plaintext shapes."""
    if 'description' in document or 'private_notes' in document:
        raise ValueError('Unsupported legacy text fields require manual review.')
    ref = document.get('reference')
    if not isinstance(ref, str) or not ref:
        raise ValueError('Case has an invalid reference.')
    result = {}
    changed = False
    for field in FIELDS:
        if field not in document:
            continue
        items = document[field]
        if not isinstance(items, list):
            raise ValueError('Case has an invalid timeline.')
        converted = []
        for item in items:
            if not isinstance(item, dict) or 'text' not in item:
                raise ValueError('Case has an invalid timeline entry.')
            item = deepcopy(item)
            if isinstance(item['text'], str):
                item['text'] = encrypt_text(item['text'], ref, field)
                changed = True
            else:
                # Verify already-encrypted data; never silently replace bad ciphertext.
                decrypt_text(item['text'], ref, field)
            converted.append(item)
        result[field] = converted
    return result, changed


def write_verified_backup(documents, destination, key_id):
    destination = destination.resolve()
    if not destination.is_relative_to(BACKUP_DIR) or destination == BACKUP_DIR:
        raise ValueError('Backup must be a new file inside data/raw/case-backups.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    cipher = _key(key_id)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='ascii') as f:
        f.write(json.dumps({'format': 'fernet-bson-jsonl-v1', 'key_id': key_id}) + '\n')
        for doc in documents:
            f.write(cipher.encrypt(BSON.encode(doc)).decode('ascii') + '\n')
        f.flush()
        os.fsync(f.fileno())
    # Verify every encrypted backup record before changing any database record.
    restored = read_backup(destination)
    if [BSON.encode(doc) for doc in restored] != [BSON.encode(doc) for doc in documents]:
        raise ValueError('Backup verification failed.')
    return destination


def read_backup(source):
    """Authenticate and decode every record before any restore can be attempted."""
    try:
        with source.open(encoding='ascii') as f:
            header = json.loads(next(f))
            if not isinstance(header, dict) or set(header) != {'format', 'key_id'} or header['format'] != 'fernet-bson-jsonl-v1':
                raise ValueError('Unsupported backup format.')
            cipher = _key(header['key_id'])
            return [BSON(cipher.decrypt(line.strip().encode('ascii'))).decode() for line in f]
    except (StopIteration, InvalidToken, UnicodeError, TypeError, json.JSONDecodeError):
        raise ValueError('Backup verification failed.') from None


def migrate(collection, apply=False, backup_path=None, key_id=None):
    documents = list(collection.find({}))
    planned = [(doc, *transform(doc)) for doc in documents]
    pending = [(doc, fields) for doc, fields, changed in planned if changed]
    if not apply:
        return len(documents), len(pending), 0
    if backup_path is None or not key_id:
        raise ValueError('A backup path and active key are required.')
    write_verified_backup(documents, backup_path, key_id)
    migrated = 0
    for doc, fields in pending:
        # Compare original arrays and version so intervening writes cannot be lost.
        query = {'_id': doc['_id']}
        for field in (*FIELDS, 'version'):
            query[field] = doc[field] if field in doc else {'$exists': False}
        result = collection.update_one(query, {'$set': fields, '$inc': {'version': 1}})
        if result.modified_count != 1:
            raise RuntimeError('A case changed during migration; stop writers and inspect before rerunning.')
        migrated += 1
    return len(documents), len(pending), migrated


def main():
    parser = argparse.ArgumentParser(description='Encrypt existing local case text; stop every app writer before applying.')
    parser.add_argument('--apply', action='store_true', help='Create and verify an encrypted backup, then migrate.')
    parser.add_argument('--offline-confirmed', action='store_true',
                        help='Confirm all application processes and other case writers are stopped.')
    args = parser.parse_args()
    if args.apply and not args.offline_confirmed:
        parser.error('--apply requires --offline-confirmed after stopping every case writer.')
    try:
        app = create_app()
        with app.app_context():
            key_id = app.config.get('CASE_ACTIVE_KEY_ID')
            _key(key_id)  # Fail closed if the key is absent or malformed.
            backup = BACKUP_DIR / ('cases-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.jsonl') if args.apply else None
            total, pending, migrated = migrate(db.get_cases(), args.apply, backup, key_id)
        print(f'Cases scanned: {total}; cases requiring encryption: {pending}; migrated: {migrated}.')
        if backup:
            print(f'Encrypted backup verified at {backup}. Keep a separate secure backup of the key.')
    except (OSError, ValueError, RuntimeError, PyMongoError, InvalidToken):
        parser.exit(1, 'Migration stopped safely. Check the key, input format, database and backup; '
                       'if interrupted, inspect and rerun only after stopping all writers.\n')


if __name__ == '__main__':
    main()
