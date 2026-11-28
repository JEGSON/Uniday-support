import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from bson import ObjectId
from cryptography.fernet import Fernet
from pymongo import MongoClient

from app import create_app
from services import cases
from services.auth import User
from services.case_crypto import CaseEncryptionError, decrypt_text, encrypt_text
from scripts import encrypt_cases


def test_encryption_wrong_key_tampering_and_context():
    with patch('db.init_app'):
        app = create_app()
    with app.app_context():
        record = encrypt_text('secret example', 'case-one', 'student_updates')
        assert 'secret example' not in repr(record)
        assert decrypt_text(record, 'case-one', 'student_updates') == 'secret example'
        with pytest.raises(CaseEncryptionError):
            decrypt_text(record, 'case-two', 'student_updates')
        with pytest.raises(CaseEncryptionError):
            decrypt_text(record, 'case-one', 'staff_notes')
        bad = dict(record, ciphertext=record['ciphertext'][:-3] + 'abc')
        with pytest.raises(CaseEncryptionError):
            decrypt_text(bad, 'case-one', 'student_updates')
        app.config['CASE_ENCRYPTION_KEYS'] = json.dumps({'test-v1': Fernet.generate_key().decode()})
        with pytest.raises(CaseEncryptionError):
            decrypt_text(record, 'case-one', 'student_updates')


def test_key_ids_preserve_old_records_and_invalid_keys_fail_closed():
    with patch('db.init_app'):
        app = create_app()
    old_key, new_key = (Fernet.generate_key().decode() for _ in range(2))
    with app.app_context():
        app.config['CASE_ENCRYPTION_KEYS'] = json.dumps({'old': old_key, 'new': new_key})
        app.config['CASE_ACTIVE_KEY_ID'] = 'old'
        old_record = encrypt_text('old content', 'case-one', 'student_updates')
        app.config['CASE_ACTIVE_KEY_ID'] = 'new'
        new_record = encrypt_text('new content', 'case-one', 'student_updates')
        assert old_record['key_id'] == 'old' and new_record['key_id'] == 'new'
        assert decrypt_text(old_record, 'case-one', 'student_updates') == 'old content'
        assert decrypt_text(new_record, 'case-one', 'student_updates') == 'new content'
        app.config['CASE_ENCRYPTION_KEYS'] = json.dumps({'new': 'é'})
        with pytest.raises(CaseEncryptionError):
            encrypt_text('content', 'case-one', 'student_updates')


def test_migration_and_new_writes_encrypt_raw_mongo(tmp_path, monkeypatch):
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('TEST_MONGODB_URI required')
    mongo = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=3000)
    name = 'unidays_test_' + uuid.uuid4().hex
    collection = mongo[name].cases
    with patch('db.init_app'):
        app = create_app()
    app.config['CASES_DB'] = name
    app.extensions['cases_mongodb'] = mongo
    backup_dir = tmp_path / 'backups'
    monkeypatch.setattr(encrypt_cases, 'BACKUP_DIR', backup_dir.resolve())
    try:
        with app.app_context():
            student = User({'_id': ObjectId(), 'role': 'student'})
            staff = User({'_id': ObjectId(), 'role': 'staff'})
            ref = cases.create_student_case(student, 'Academic', 'new-secret-marker', False)
            raw = collection.find_one({'reference': ref})
            assert 'new-secret-marker' not in repr(raw)
            assert 'new-secret-marker' in repr(cases.get_student_case(student, ref))
            assert cases.claim_case(staff, ref)
            assert cases.update_staff_case(staff, ref, 'note', 'private-secret-marker', 1)
            assert 'private-secret-marker' not in repr(collection.find_one({'reference': ref}))
            assert 'private-secret-marker' in repr(cases.get_staff_case(staff, ref))
            raw['reference'] = 'b' * 32
            raw['_id'] = ObjectId()
            raw['student_updates'][0]['text'] = 'legacy-secret-marker'
            raw.pop('version', None)
            collection.insert_one(raw)
            assert encrypt_cases.migrate(collection) == (2, 1, 0)
            backup = backup_dir / 'backup.jsonl'
            assert encrypt_cases.migrate(collection, True, backup, 'test-v1') == (2, 1, 1)
            assert b'legacy-secret-marker' not in backup.read_bytes()
            migrated = collection.find_one({'reference': 'b' * 32})
            assert 'legacy-secret-marker' not in repr(migrated)
            assert decrypt_text(migrated['student_updates'][0]['text'], 'b' * 32, 'student_updates') == 'legacy-secret-marker'
            assert migrated['version'] == 1
            assert encrypt_cases.migrate(collection) == (2, 0, 0)
    finally:
        mongo.drop_database(name)
        mongo.close()


def test_migration_rejects_unknown_plaintext_fields_before_writes():
    with patch('db.init_app'):
        app = create_app()
    with app.app_context():
        with pytest.raises(ValueError, match='Unsupported'):
            encrypt_cases.transform({'reference': 'a' * 32, 'description': 'legacy secret'})
