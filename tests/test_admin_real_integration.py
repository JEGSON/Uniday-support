import os
import re
import time
import uuid
from unittest.mock import patch
import pytest
from bson import ObjectId
from pymongo import MongoClient
from app import create_app
from services.auth import User
from services import admin_users


@pytest.fixture
def context():
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('TEST_MONGODB_URI required')
    mongo = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=3000)
    name = 'unidays_test_' + uuid.uuid4().hex
    with patch('db.init_app'):
        app = create_app()
    app.config.update(TESTING=True, MONGODB_AUTH_DB=name, MONGODB_AUDIT_DB=name, CASES_DB=name)
    app.extensions.update(mongodb=mongo, stats_mongodb=mongo, audit_writer=mongo, audit_reader=mongo)
    app.login_manager.session_protection = None
    yield app, mongo[name]
    mongo.drop_database(name)
    mongo.close()


def test_admin_user_changes_and_audit(context):
    app, database = context
    admin_id, other_id, student_id = ObjectId(), ObjectId(), ObjectId()
    database.users.insert_many([{'_id': admin_id, 'role': 'admin', 'is_active': True, 'full_name': 'Admin', 'email': 'a@example.edu'},
                                {'_id': other_id, 'role': 'admin', 'is_active': True, 'full_name': 'Other', 'email': 'b@example.edu'},
                                {'_id': student_id, 'role': 'student', 'is_active': True, 'full_name': 'Student', 'email': 'c@example.edu', 'password_hash': 'secretmarker', 'email_verified': True, 'student_identity_verified': True}])
    app.login_manager.user_loader(lambda uid: User(database.users.find_one({'_id': ObjectId(uid), 'is_active': True})) if database.users.find_one({'_id': ObjectId(uid), 'is_active': True}) else None)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=str(admin_id), _fresh=True, last_activity=time.time())
    page = client.get('/admin/users').get_data(as_text=True)
    assert 'secretmarker' not in page
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    def post(target, action, **data):
        return client.post('/admin/users/' + str(target) + '/' + action, data={'csrf_token': csrf, **data})
    assert post(admin_id, 'status', status='deactivate').status_code == 403
    assert post(other_id, 'role', role='student').status_code == 403
    assert post(student_id, 'role', role='{"$ne":""}').status_code == 400
    assert post(student_id, 'role', role='admin').status_code == 403
    assert post(student_id, 'status', status='deactivate').status_code == 302
    assert not database.users.find_one({'_id': student_id})['is_active']
    assert database.events.find_one({'event_type': 'user_deactivated', 'target_id': student_id})
    assert post(student_id, 'status', status='activate').status_code == 302
    assert database.events.find_one({'event_type': 'user_activated', 'target_id': student_id})
    assert database.events.count_documents({'event_type': 'admin_action_denied'}) >= 3
    with app.app_context():
        with pytest.raises(ValueError):
            admin_users.change_user(User({'_id': admin_id, 'role': 'admin'}), {'$ne': ''}, 'status', 'deactivate')


def test_overview_never_returns_case_content(context):
    app, database = context
    from datetime import datetime, timezone
    admin_id = ObjectId()
    database.users.insert_one({'_id': admin_id, 'role': 'admin', 'is_active': True})
    database.cases.insert_one({'status': 'Received', 'category': 'Wellbeing', 'student_updates': [{'text': 'uniquedescriptionmarker'}], 'staff_notes': [{'text': 'uniquestaffnotemarker'}]})
    app.login_manager.user_loader(lambda uid: User(database.users.find_one({'_id': ObjectId(uid)})))
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=str(admin_id), _fresh=True, last_activity=time.time())
    page = client.get('/admin/home')
    assert page.status_code == 200
    assert b'uniquedescriptionmarker' not in page.data and b'uniquestaffnotemarker' not in page.data


def test_deactivation_blocks_existing_session_on_next_request(context):
    app, database = context
    student_id = ObjectId()
    database.users.insert_one({'_id': student_id, 'role': 'student', 'is_active': True, 'email': 'student@example.edu'})
    # Register the real loader so each request reads current account state.
    from services.auth import load_user
    app.login_manager.user_loader(load_user)
    app.extensions['cases_mongodb'] = app.extensions['mongodb']
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=str(student_id), _fresh=True, last_activity=time.time())
    assert client.get('/student/home').status_code == 200
    database.users.update_one({'_id': student_id}, {'$set': {'is_active': False}})
    assert client.get('/student/home').status_code == 302


def test_role_change_audited_and_requires_identity(context):
    app, database = context
    admin_id, student_id = ObjectId(), ObjectId()
    database.users.insert_many([{'_id': admin_id, 'role': 'admin', 'is_active': True, 'email': 'admin@example.edu'},
                                {'_id': student_id, 'role': 'staff', 'is_active': True, 'email': 'student@example.edu', 'student_identity_verified': True, 'email_verified': True}])
    app.login_manager.user_loader(lambda uid: User(database.users.find_one({'_id': ObjectId(uid)})))
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=str(admin_id), _fresh=True, last_activity=time.time())
    page = client.get('/admin/users').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    response = client.post('/admin/users/' + str(student_id) + '/role', data={'csrf_token': csrf, 'role': 'student'})
    assert response.status_code == 302
    assert database.users.find_one({'_id': student_id})['role'] == 'student'
    assert database.events.find_one({'event_type': 'role_changed', 'target_id': student_id, 'old_role': 'staff', 'new_role': 'student'})
