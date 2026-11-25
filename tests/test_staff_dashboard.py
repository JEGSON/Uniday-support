import re
import time
from unittest.mock import patch

import pytest
from bson import ObjectId

from app import create_app
from services.auth import User


@pytest.fixture
def make_client():
    def build(role=None):
        account = User({'_id': ObjectId(), 'role': role}) if role else None
        with patch('db.init_app'), patch('services.auth.load_user', return_value=account):
            app = create_app()
        app.config['TESTING'] = True
        app.login_manager.session_protection = None
        client = app.test_client()
        if account:
            with client.session_transaction() as session:
                session['_user_id'] = account.id
                session['_fresh'] = True
                session['last_activity'] = time.time()
        return client
    return build


def test_staff_routes_require_staff_role(make_client):
    assert make_client().get('/staff/home').status_code == 302
    for role in ('student', 'admin'):
        with patch('services.audit.record') as audit:
            assert make_client(role).get('/staff/cases/' + 'a' * 32).status_code == 403
            audit.assert_called_once()


def test_claim_requires_csrf_and_handles_conflict(make_client):
    client = make_client('staff')
    ref = 'a' * 32
    assert client.post('/staff/cases/' + ref + '/claim').status_code == 400
    with patch('services.cases.staff_queue', return_value=[]):
        page = client.get('/staff/home').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    with patch('services.cases.claim_case', return_value=False):
        assert client.post('/staff/cases/' + ref + '/claim', data={'csrf_token': csrf}).status_code == 409


def test_unavailable_staff_storage_returns_error(make_client):
    with patch('services.cases.staff_queue', side_effect=RuntimeError()):
        assert make_client('staff').get('/staff/home').status_code == 503
