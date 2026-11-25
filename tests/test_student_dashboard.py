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
        with patch('services.audit.record') as audit:
            assert make_client(role).get('/student/home').status_code == 403
            audit.assert_called_once()


def test_unavailable_storage_is_not_shown_as_empty(make_client):
    with patch('services.cases.get_student_cases', side_effect=RuntimeError()):
        page = make_client('student').get('/student/home')
    assert page.status_code == 503 and b'temporarily unavailable' in page.data
    assert b'Nothing here yet' not in page.data


def test_submission_validation_and_csrf(make_client):
    client = make_client('student')
    data = {'category': 'Academic', 'description': 'Example request'}
    assert client.post('/student/requests/new', data=data).status_code == 400
    page = client.get('/student/requests/new').get_data(as_text=True)
    data['csrf_token'] = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    with patch('services.cases.create_student_case', return_value='a' * 32) as create:
        response = client.post('/student/requests/new', data=data)
        assert response.status_code == 302 and response.location.endswith('a' * 32)
        create.assert_called_once()
    data['category'] = 'not-a-category'
    assert client.post('/student/requests/new', data=data).status_code == 400
