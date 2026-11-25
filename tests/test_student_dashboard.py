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


def test_anonymous_redirect_and_other_roles_forbidden(make_client):
    assert make_client().get('/student/home').status_code == 302
    for role in ('staff', 'admin'):
        client = make_client(role)
        with patch('services.audit.record') as audit:
            assert client.get('/student/home').status_code == 403
            audit.assert_called_once()


def test_student_views_never_render_internal_notes(make_client):
    client = make_client('student')
    for path in ('/student/home', '/student/requests/REQ-1042', '/student/requests/REQ-1031'):
        response = client.get(path)
        assert response.status_code == 200
        assert b'Fictional internal note' not in response.data
        assert b'private_notes' not in response.data
    assert client.get('/student/requests/REQ-NOT-FOUND').status_code == 404


def test_preview_form_requires_csrf_and_never_claims_submission(make_client):
    client = make_client('student')
    data = {'category': 'Academic', 'description': 'Example request'}
    assert client.post('/student/requests/new', data=data).status_code == 400
    page = client.get('/student/requests/new').get_data(as_text=True)
    data['csrf_token'] = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post('/student/requests/new', data=data)
    assert response.status_code == 200 and b'not been sent or saved' in response.data
    data['category'] = 'not-a-category'
    assert client.post('/student/requests/new', data=data).status_code == 400


def test_reply_is_only_shown_for_waiting_case(make_client):
    client = make_client('student')
    assert b'Reply when you' not in client.get('/student/requests/REQ-1042').data
    assert b'Reply when you' in client.get('/student/requests/REQ-1031').data
