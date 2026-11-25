"""Real MongoDB tests run only against an isolated, disposable test database."""
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
from services import cases


@pytest.fixture
def setup_cases():
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('Set TEST_MONGODB_URI to run isolated MongoDB integration tests.')
    mongo = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=3000)
    name = 'unidays_test_' + uuid.uuid4().hex
    collection = mongo[name].cases
    with patch('db.init_app'):
        app = create_app()
    app.config['TESTING'] = True
    app.login_manager.session_protection = None
    app.extensions['cases_mongodb'] = mongo
    app.config['CASES_DB'] = name
    yield app, collection
    mongo.drop_database(name)
    mongo.close()


def test_owner_scoping_status_and_projection(setup_cases):
    app, collection = setup_cases
    first = User({'_id': ObjectId(), 'role': 'student'})
    second = User({'_id': ObjectId(), 'role': 'student'})
    with app.app_context():
        reference = cases.create_student_case(first, 'Wellbeing', 'Fictional request', False)
        assert cases.get_student_case(second, reference) is None
        assert cases.get_student_cases(second) == []
        assert not cases.add_student_reply(second, reference, 'Forged reply')
        assert not cases.add_student_reply(first, reference, 'Too early')
        collection.update_one({'reference': reference}, {'$set': {'status': 'Awaiting Student', 'private_notes': 'Never expose this'}})
        assert 'Never expose this' not in repr(cases.get_student_case(first, reference))
        assert cases.add_student_reply(first, reference, 'A genuine response')
        assert not cases.add_student_reply(first, reference, 'Double submit')
        assert cases.get_student_case(first, reference)['status'] == 'In progress'
        assert cases.get_student_case(first, {'$ne': ''}) is None


def test_student_form_persists_and_other_student_gets_404(setup_cases):
    app, collection = setup_cases
    first = User({'_id': ObjectId(), 'role': 'student'})
    second = User({'_id': ObjectId(), 'role': 'student'})
    client = app.test_client()
    app.login_manager.user_loader(lambda user_id: first if user_id == first.id else second)
    with client.session_transaction() as session:
        session.update(_user_id=first.id, _fresh=True, last_activity=time.time())
    with patch('services.auth.load_user', return_value=first):
        page = client.get('/student/requests/new').get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        result = client.post('/student/requests/new', data={'csrf_token': token, 'category': 'Academic', 'description': 'Test only'})
        assert result.status_code == 302
        assert b'Test only' in client.get(result.location).data
        assert collection.count_documents({'owner_id': ObjectId(first.id)}) == 1
    with client.session_transaction() as session:
        session.update(_user_id=second.id, _fresh=True, last_activity=time.time())
    with patch('services.auth.load_user', return_value=second):
        assert client.get(result.location).status_code == 404
        assert b'Test only' not in client.get('/student/home').data


def test_concurrent_claims_and_assigned_access(setup_cases):
    from concurrent.futures import ThreadPoolExecutor
    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    officers = [User({'_id': ObjectId(), 'role': 'staff'}) for _ in range(2)]
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'A private description', False)
        queue = cases.staff_queue(officers[0])
        assert len(queue) == 1 and 'A private description' not in repr(queue)
        assert cases.get_staff_case(officers[0], reference) is None
    def claim(officer):
        with app.app_context():
            return cases.claim_case(officer, reference)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, officers))
    assert sum(results) == 1
    winner = officers[results.index(True)]
    loser = officers[results.index(False)]
    with app.app_context():
        assert cases.get_staff_case(loser, reference) is None
        assert not cases.update_staff_case(loser, reference, 'note', 'Unauthorized')
        assert not cases.staff_queue(loser)
        assert cases.update_staff_case(winner, reference, 'note', 'Staff secret')
        assert cases.update_staff_case(winner, reference, 'message', 'Please tell us more')
        assert cases.update_staff_case(winner, reference, 'status', 'Awaiting Student')
        student_view = cases.get_student_case(student, reference)
        assert 'Staff secret' not in repr(student_view)
        assert 'Please tell us more' in repr(student_view)
        assert cases.add_student_reply(student, reference, 'Here is my reply')
        assert 'Here is my reply' in repr(cases.get_staff_case(winner, reference))
        assert cases.update_staff_case(winner, reference, 'archive')
        assert cases.get_staff_case(winner, reference) is None
        assert cases.get_student_case(student, reference) is not None


def test_staff_workflow_http_and_private_notes(setup_cases):
    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    other = User({'_id': ObjectId(), 'role': 'staff'})
    accounts = {u.id: u for u in (student, staff, other)}
    app.login_manager.user_loader(lambda user_id: accounts.get(user_id))
    client = app.test_client()
    with app.app_context():
        ref = cases.create_student_case(student, 'Academic', 'Fictional request', False)
    with client.session_transaction() as session:
        session.update(_user_id=staff.id, _fresh=True, last_activity=time.time())
    page = client.get('/staff/home').get_data(as_text=True)
    assert ref in page and 'Fictional request' not in page
    assert client.get('/staff/cases/' + ref).status_code == 404
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    with patch('services.audit.record'):
        assert client.post('/staff/cases/' + ref + '/claim', data={'csrf_token': csrf}).status_code == 302
        assert b'Fictional request' in client.get('/staff/cases/' + ref).data
        assert client.post('/staff/cases/' + ref, data={'csrf_token': csrf, 'action': 'note', 'note': 'Private test note'}).status_code == 302
        assert client.post('/staff/cases/' + ref, data={'csrf_token': csrf, 'action': 'message', 'message': 'Visible update'}).status_code == 302
        assert client.post('/staff/cases/' + ref, data={'csrf_token': csrf, 'action': 'status', 'status': 'Awaiting Student'}).status_code == 302
    with client.session_transaction() as session:
        session.update(_user_id=other.id, _fresh=True, last_activity=time.time())
    assert client.get('/staff/cases/' + ref).status_code == 404
    assert client.post('/staff/cases/' + ref, data={'csrf_token': csrf, 'action': 'note', 'note': 'Forged'}).status_code == 404
    with client.session_transaction() as session:
        session.update(_user_id=student.id, _fresh=True, last_activity=time.time())
    student_page = client.get('/student/requests/' + ref)
    assert b'Visible update' in student_page.data and b'Private test note' not in student_page.data
    assert b'Reply when you' in student_page.data
