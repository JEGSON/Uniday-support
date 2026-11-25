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
