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
                session.update(_user_id=account.id, _fresh=True, last_activity=time.time())
        return client
    return build


@pytest.mark.parametrize('url', ['/admin/home', '/admin/users', '/admin/audit'])
def test_admin_pages_require_admin_role(make_client, url):
    assert make_client().get(url).status_code == 302
    for role in ('student', 'staff'):
        with patch('services.audit.record') as audit:
            assert make_client(role).get(url).status_code == 403
            audit.assert_called_once()


def test_admin_page_projections_and_csrf(make_client):
    client = make_client('admin')
    with patch('services.stats.get_admin_overview', return_value={'open_requests': 1, 'awaiting_reply': 0, 'categories': []}):
        response = client.get('/admin/home')
        assert response.status_code == 200 and b'Fictional internal note' not in response.data
    with patch('services.admin_users.list_users', return_value=[]):
        assert client.get('/admin/users').status_code == 200
    with patch('services.audit_viewer.get_events', return_value=([], 1, False)):
        assert client.get('/admin/audit?type=unknown').status_code == 200
    assert client.post('/admin/users/' + 'a' * 24 + '/status').status_code == 400


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
    assert response.status_code == 302 and response.headers['Location'].endswith('/admin/home')
