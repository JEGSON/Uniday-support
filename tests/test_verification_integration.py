"""Optional real-Mongo integration tests; requires TEST_MONGODB_URI."""
import os
import re
import uuid
import json
from urllib.request import urlopen
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from pymongo import MongoClient

import db
from app import create_app
from services import enrollment


@pytest.fixture
def setup_db():
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('Set TEST_MONGODB_URI to run isolated MongoDB integration tests.')
    mongo = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=3000)
    name = 'unidays_test_' + uuid.uuid4().hex
    database = mongo[name]

    def initialize(app):
        app.extensions['mongodb'] = mongo
        app.config['MONGODB_AUTH_DB'] = name
        app.config['MONGODB_AUDIT_DB'] = name

    with patch('db.init_app', side_effect=initialize):
        app = create_app()
    app.config['TESTING'] = True
    database.student_registry.insert_one({'student_id': 'DEMO001', 'university_email': 'alex@example.edu',
                                           'full_name': 'Alex Example', 'course': 'Computing', 'claimed': False})
    with patch('db.get_registry', return_value=database.student_registry):
        yield app, database
    mongo.drop_database(name)
    mongo.close()


def csrf(client, path):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).get_data(as_text=True)).group(1)


def signup(client, **changes):
    data = {'full_name': 'Alex Example', 'student_id': 'DEMO001', 'email': 'alex@example.edu',
            'course': 'Computing', 'password': 'initial password is not used',
            'confirm_password': 'initial password is not used', 'csrf_token': csrf(client, '/signup')}
    data.update(changes)
    return client.post('/signup', data=data)


def test_signup_verify_replay_and_signin(setup_db):
    app, database = setup_db
    client = app.test_client()
    with patch('services.mail.send_verification_email') as send:
        assert signup(client, role='admin').status_code == 200
    token = send.call_args.args[1]
    user = database.users.find_one({'student_id': 'DEMO001'})
    assert user['is_active'] is False and user['password_hash'] is None
    assert user['role'] == 'student'  # A forged public role cannot grant privileges.
    assert database.student_registry.find_one({'student_id': 'DEMO001'})['claimed'] is True
    assert client.get('/verify-email').status_code == 200
    assert database.users.find_one({'_id': user['_id']})['is_active'] is False
    data = {'token': token, 'password': 'new mailbox owner password', 'confirm_password': 'new mailbox owner password',
            'csrf_token': csrf(client, '/verify-email')}
    assert b'Your account is ready' in client.post('/verify-email', data=data).data
    assert database.users.find_one({'_id': user['_id']})['is_active'] is True
    bad_login = {'csrf_token': csrf(client, '/signin'), 'identifier': 'alex@example.edu',
                 'password': 'initial password is not used'}
    assert client.post('/signin', data=bad_login).status_code == 401
    assert b'invalid or has expired' in client.post('/verify-email', data=data).data
    login = {'csrf_token': csrf(client, '/signin'), 'identifier': 'alex@example.edu', 'password': data['password']}
    assert client.post('/signin', data=login).status_code == 302
    assert client.get('/account').status_code == 200
    assert client.get('/logout').status_code == 405
    assert client.post('/logout').status_code == 400
    logout_csrf = re.search(r'name="csrf_token" value="([^"]+)"', client.get('/account').get_data(as_text=True)).group(1)
    assert client.post('/logout', data={'csrf_token': logout_csrf}).status_code == 302
    assert client.get('/account').status_code == 302


def test_wrong_registry_details_and_simultaneous_claim(setup_db):
    app, database = setup_db
    with patch('services.mail.send_verification_email'):
        client = app.test_client()
        wrong = signup(client, email='wrong@example.edu')
        unknown = signup(client, student_id='NOTFOUND')
        assert wrong.status_code == unknown.status_code == 200
        assert database.users.count_documents({}) == 0
        values = {'student_id': 'DEMO001', 'email': 'alex@example.edu'}
        def claim():
            with app.app_context():
                enrollment.register(values)
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: claim(), range(2)))
        assert database.users.count_documents({}) == 1
        assert signup(client).status_code == 200
        assert database.users.count_documents({}) == 1


def test_expired_tampered_resend_and_inactive_signin(setup_db):
    app, database = setup_db
    client = app.test_client()
    with patch('services.mail.send_verification_email') as send:
        signup(client)
        token = send.call_args.args[1]
        # A second delivery within the account cooldown must not be sent.
        resend_csrf = csrf(client, '/resend-verification')
        response = client.post('/resend-verification', data={'csrf_token': resend_csrf, 'email': 'alex@example.edu'})
        assert response.status_code == 200 and send.call_count == 1
    login = {'csrf_token': csrf(client, '/signin'), 'identifier': 'alex@example.edu',
             'password': 'initial password is not used'}
    assert client.post('/signin', data=login).status_code == 401
    data = {'csrf_token': csrf(client, '/verify-email'), 'token': 'x' * 43,
            'password': 'a new secure passphrase', 'confirm_password': 'a new secure passphrase'}
    assert b'invalid or has expired' in client.post('/verify-email', data=data).data
    database.users.update_one({'student_id': 'DEMO001'}, {'$set': {'verification_expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}})
    data['token'] = token
    assert b'invalid or has expired' in client.post('/verify-email', data=data).data
    assert database.users.find_one({'student_id': 'DEMO001'})['is_active'] is False


def test_mail_failure_leaves_inactive_and_resend_available(setup_db):
    app, database = setup_db
    client = app.test_client()
    with patch('services.mail.send_verification_email', side_effect=OSError('smtp unavailable')):
        assert signup(client).status_code == 200
    user = database.users.find_one({'student_id': 'DEMO001'})
    assert user['is_active'] is False
    database.users.update_one({'_id': user['_id']}, {'$set': {'verification_sent_at': datetime.now(timezone.utc) - timedelta(minutes=2)}})
    with patch('services.mail.send_verification_email') as send:
        response = client.post('/resend-verification', data={'csrf_token': csrf(client, '/resend-verification'),
                                                             'email': 'alex@example.edu'})
        assert response.status_code == 200 and send.call_count == 1


def test_verification_csrf_and_password_retry(setup_db):
    app, database = setup_db
    client = app.test_client()
    with patch('services.mail.send_verification_email') as send:
        signup(client)
    token = send.call_args.args[1]
    assert client.post('/verify-email', data={'token': token}).status_code == 400
    data = {'csrf_token': csrf(client, '/verify-email'), 'token': token,
            'password': 'short', 'confirm_password': 'short'}
    response = client.post('/verify-email', data=data)
    assert b'Choose matching passwords' in response.data and token.encode() in response.data
    assert database.users.find_one({'student_id': 'DEMO001'})['is_active'] is False


def test_resend_ip_rate_limit(setup_db):
    app, _ = setup_db
    client = app.test_client()
    data = {'csrf_token': csrf(client, '/resend-verification'), 'email': 'unknown@example.edu'}
    assert [client.post('/resend-verification', data=data).status_code for _ in range(6)] == [200] * 5 + [429]


def test_unmatched_legacy_account_cannot_receive_token(setup_db):
    app, database = setup_db
    database.users.insert_one({'email': 'unverified@example.edu', 'role': 'student', 'is_active': False,
                               'student_identity_verified': False})
    client = app.test_client()
    with patch('services.mail.send_verification_email') as send:
        response = client.post('/resend-verification', data={'csrf_token': csrf(client, '/resend-verification'),
                                                             'email': 'unverified@example.edu'})
    assert response.status_code == 200
    send.assert_not_called()


def test_account_lockout_after_failed_passwords(setup_db):
    app, database = setup_db
    client = app.test_client()
    with patch('services.mail.send_verification_email') as send:
        signup(client)
    data = {'csrf_token': csrf(client, '/verify-email'), 'token': send.call_args.args[1],
            'password': 'my verified account passphrase', 'confirm_password': 'my verified account passphrase'}
    client.post('/verify-email', data=data)
    login = {'csrf_token': csrf(client, '/signin'), 'identifier': 'alex@example.edu', 'password': 'incorrect'}
    assert [client.post('/signin', data=login).status_code for _ in range(5)] == [401] * 5
    login['password'] = data['password']
    assert client.post('/signin', data=login).status_code == 401
    assert database.users.find_one({'email': 'alex@example.edu'})['locked_until'] is not None


def test_end_to_end_via_real_mailpit(setup_db):
    if os.environ.get('TEST_MAILPIT') != '1':
        pytest.skip('Set TEST_MAILPIT=1 to test local SMTP and inbox.')
    from services.tokens import token_hash
    app, database = setup_db
    client = app.test_client()
    assert signup(client).status_code == 200
    user = database.users.find_one({'student_id': 'DEMO001'})
    with urlopen('http://127.0.0.1:8025/api/v1/messages', timeout=5) as response:
        messages = json.load(response)['messages']
    token = None
    for item in messages:
        if item.get('Subject') != 'Verify your Unidays Support account':
            continue
        with urlopen('http://127.0.0.1:8025/api/v1/message/' + item['ID'], timeout=5) as response:
            body = json.load(response).get('Text', '')
        found = re.search(r'#token=([A-Za-z0-9_-]{43})', body)
        if found and token_hash(found.group(1)) == user['verification_hash']:
            token = found.group(1)
            break
    assert token is not None
    data = {'csrf_token': csrf(client, '/verify-email'), 'token': token,
            'password': 'my new mailbox owner password', 'confirm_password': 'my new mailbox owner password'}
    assert b'Your account is ready' in client.post('/verify-email', data=data).data
    assert database.users.find_one({'_id': user['_id']})['is_active'] is True
