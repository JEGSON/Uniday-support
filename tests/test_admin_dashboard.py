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


@pytest.mark.parametrize('url', ['/admin/home', '/admin/users', '/admin/audit'])
def test_admin_pages_require_admin_role(make_client, url):
    assert make_client().get(url).status_code == 302
    for role in ('student', 'staff'):
        with patch('services.audit.record') as audit:
            assert make_client(role).get(url).status_code == 403
            audit.assert_called_once()


def test_admin_pages_only_expose_example_oversight_data(make_client):
    client = make_client('admin')
    for url in ('/admin/home', '/admin/users', '/admin/audit'):
        response = client.get(url)
        assert response.status_code == 200
        assert b'fictional' in response.data
        assert b'Fictional internal note' not in response.data
        assert b'I would like to talk through my options' not in response.data
    filtered = client.get('/admin/audit?type=Access')
    assert b'was denied access' in filtered.data
    assert b'created a staff account' not in filtered.data


def test_admin_preview_actions_are_csrf_protected_and_do_not_persist(make_client):
    client = make_client('admin')
    assert client.post('/admin/users', data={'action': 'status', 'target': 'USR-1001'}).status_code == 400
    page = client.get('/admin/users').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post('/admin/users', data={'csrf_token': csrf, 'action': 'role', 'target': 'USR-1001', 'role': 'admin'})
    assert response.status_code == 200 and b'No account changes have been saved' in response.data
    assert b'USR-1001' in client.get('/admin/users').data
    assert client.post('/admin/users', data={'csrf_token': csrf, 'action': 'role', 'target': 'USR-1001', 'role': 'invalid'}).status_code == 400
    assert client.post('/admin/users', data={'csrf_token': csrf, 'action': 'status', 'target': 'unknown'}).status_code == 400


def test_admin_signin_redirects_to_overview():
    account = User({'_id': ObjectId(), 'role': 'admin'})
    with patch('db.init_app'):
        app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()
    page = client.get('/signin').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    with patch('services.auth.authenticate', return_value=account), patch('services.audit.record'):
        response = client.post('/signin', data={'csrf_token': csrf, 'identifier': 'admin@example.edu', 'password': 'example'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/home')
