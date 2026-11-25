import re
from unittest.mock import Mock, patch

import pytest
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

from app import create_app
from services.passwords import verify_password
from services.users import validate_signup


@pytest.fixture
def client():
    with patch('db.ensure_user_indexes'):
        app = create_app()
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture
def details():
    return {'full_name': 'Test Student', 'student_id': 'st-123', 'email': 'Student@Example.com',
            'course': 'Computer Science', 'password': 'a unique long passphrase',
            'confirm_password': 'a unique long passphrase', 'role': 'admin'}


def token(client):
    page = client.get('/signup').get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)


def test_signup_creates_student_and_hides_duplicate(client, details):
    details['csrf_token'] = token(client)
    with patch('services.enrollment.register') as register:
        first = client.post('/signup', data=details)
        saved = register.call_args.args[0]
        assert saved['email'] == 'student@example.com'
        assert saved['student_id'] == 'ST-123'
        assert 'role' not in saved and 'password' not in saved
        register.side_effect = DuplicateKeyError('duplicate')
        duplicate = client.post('/signup', data=details)
    assert first.status_code == duplicate.status_code == 200
    # CSRF token signatures may differ when responses cross a clock boundary.
    strip_token = lambda body: re.sub(rb'name="csrf_token" value="[^"]+"', b'name="csrf_token" value="TOKEN"', body)
    assert strip_token(first.data) == strip_token(duplicate.data)


def test_signup_requires_csrf_and_rejects_weak_password(client, details):
    assert client.post('/signup', data=details).status_code == 400
    details.update(csrf_token=token(client), password='short', confirm_password='short')
    with patch('services.enrollment.register') as get_users:
        response = client.post('/signup', data=details)
    assert response.status_code == 400
    get_users.assert_not_called()


def test_unavailable_database_returns_generic_error(client, details):
    details['csrf_token'] = token(client)
    with patch('services.enrollment.register', side_effect=ServerSelectionTimeoutError('unavailable')):
        response = client.post('/signup', data=details)
    assert response.status_code == 503
    assert b'Account creation is currently unavailable' in response.data


@pytest.mark.parametrize('field', ['full_name', 'student_id', 'email', 'course', 'password', 'confirm_password'])
def test_operator_shaped_values_are_rejected(details, field):
    details[field] = {'$ne': ''}
    _, errors = validate_signup(details)
    assert field in errors


def test_signup_rate_limit(client, details):
    details['csrf_token'] = token(client)
    with patch('services.enrollment.register'):
        responses = [client.post('/signup', data=details) for _ in range(6)]
    assert [response.status_code for response in responses] == [200] * 5 + [429]


def test_signin_rate_limit(client):
    page = client.get('/signin').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    with patch('services.auth.authenticate', return_value=None), patch('services.audit.record'):
        responses = [client.post('/signin', data={'csrf_token': csrf, 'identifier': 'test', 'password': 'anything'})
                     for _ in range(11)]
    assert [response.status_code for response in responses] == [401] * 10 + [429]
