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
            assert make_client(role).get('/staff/cases/REQ-1042').status_code == 403
            audit.assert_called_once()


def test_staff_queue_filters_and_detail_privacy(make_client):
    client = make_client('staff')
    page = client.get('/staff/home')
    assert page.status_code == 200 and b'fictional' in page.data
    filtered = client.get('/staff/home?status=New')
    assert b'REQ-1042' in filtered.data and b'REQ-1031' not in filtered.data
    detail = client.get('/staff/cases/REQ-1042')
    assert detail.status_code == 200 and b'Fictional internal note.' in detail.data
    assert b'VISIBLE TO STAFF ONLY' in detail.data and b'SHARED WITH THE STUDENT' in detail.data
    assert client.get('/staff/cases/NOT-FOUND').status_code == 404
    assert b'Fictional internal note.' not in make_client('student').get('/student/home').data


def test_staff_preview_actions_require_csrf_and_do_not_persist(make_client):
    client = make_client('staff')
    url = '/staff/cases/REQ-1042'
    assert client.post(url, data={'action': 'archive'}).status_code == 400
    page = client.get(url).get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post(url, data={'csrf_token': csrf, 'action': 'archive'})
    assert response.status_code == 200 and b'No changes have been saved' in response.data
    assert b'Fictional internal note.' in client.get(url).data
    assert client.post(url, data={'csrf_token': csrf, 'action': 'status', 'status': 'injected'}).status_code == 400
