"""Each test gets an independent encryption key, never the developer's local key."""
import json
import pytest
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def isolated_case_key(monkeypatch):
    monkeypatch.setenv('CASE_ACTIVE_KEY_ID', 'test-v1')
    monkeypatch.setenv('CASE_ENCRYPTION_KEYS', json.dumps({'test-v1': Fernet.generate_key().decode()}))
