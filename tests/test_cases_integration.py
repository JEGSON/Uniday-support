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
    app.extensions['mongodb'] = mongo
    app.config['CASES_DB'] = name
    app.config['MONGODB_AUTH_DB'] = name
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
        assert cases.update_staff_case(loser, reference, 'note', 'Unauthorized', 1) is None
        assert not cases.staff_queue(loser)
        assert cases.update_staff_case(winner, reference, 'note', 'Staff secret', 1) is not None
        assert cases.update_staff_case(winner, reference, 'message', 'Please tell us more', 2) is not None
        assert cases.update_staff_case(winner, reference, 'status', 'Awaiting Student', 3) is not None
        student_view = cases.get_student_case(student, reference)
        assert 'Staff secret' not in repr(student_view)
        assert 'Please tell us more' in repr(student_view)
        assert cases.add_student_reply(student, reference, 'Here is my reply')
        assert 'Here is my reply' in repr(cases.get_staff_case(winner, reference))
        assert cases.update_staff_case(winner, reference, 'archive', expected_version=5) is not None
        assert cases.get_staff_case(winner, reference) is None
        assert cases.get_student_case(student, reference) is None


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
        for version, action, key, value in [(1, 'note', 'note', 'Private test note'),
                                            (2, 'message', 'message', 'Visible update'),
                                            (3, 'status', 'status', 'Awaiting Student')]:
            assert client.post('/staff/cases/' + ref, data={'csrf_token': csrf, 'version': version, 'action': action, key: value}).status_code == 302
    with client.session_transaction() as session:
        session.update(_user_id=other.id, _fresh=True, last_activity=time.time())
    assert client.get('/staff/cases/' + ref).status_code == 404
    assert client.post('/staff/cases/' + ref, data={'csrf_token': csrf, 'action': 'note', 'note': 'Forged'}).status_code == 404
    with client.session_transaction() as session:
        session.update(_user_id=student.id, _fresh=True, last_activity=time.time())
    student_page = client.get('/student/requests/' + ref)
    assert b'Visible update' in student_page.data and b'Private test note' not in student_page.data
    assert b'Reply when you' in student_page.data


def test_student_forgery_xss_denial_and_audit_events(setup_cases):
    app, collection = setup_cases
    database = collection.database
    app.extensions['audit_writer'] = collection.database.client
    app.config['MONGODB_AUDIT_DB'] = database.name
    first = User({'_id': ObjectId(), 'role': 'student'})
    second = User({'_id': ObjectId(), 'role': 'student'})
    accounts = {u.id: u for u in (first, second)}
    app.login_manager.user_loader(lambda uid: accounts.get(uid))
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=first.id, _fresh=True, last_activity=time.time())
    form = client.get('/student/requests/new').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', form).group(1)
    payload = '<script>alert("xss")</script>'
    data = {'csrf_token': csrf, 'category': 'Academic', 'description': payload,
            'urgent': 'yes', 'owner_id': second.id, 'status': 'Done', 'assigned_to': second.id}
    created = client.post('/student/requests/new', data=data)
    assert created.status_code == 302
    ref = created.location.rsplit('/', 1)[-1]
    document = collection.find_one({'reference': ref})
    assert document['owner_id'] == ObjectId(first.id) and document['status'] == 'New'
    assert 'assigned_to' not in document and document['urgent'] is True
    html = client.get(created.location).get_data(as_text=True)
    assert payload not in html and '&lt;script&gt;' in html
    assert database.events.count_documents({'event_type': 'case_created', 'case_reference': ref}) == 1
    invalid = dict(data, urgent='operator')
    assert client.post('/student/requests/new', data=invalid).status_code == 400
    assert collection.count_documents({}) == 1
    with client.session_transaction() as session:
        session.update(_user_id=second.id, _fresh=True, last_activity=time.time())
    assert client.get(created.location).status_code == 404
    event = database.events.find_one({'event_type': 'case_viewed_denied'})
    assert event and 'case_reference' not in event and payload not in repr(event)
    with client.session_transaction() as session:
        session.update(_user_id=first.id, _fresh=True, last_activity=time.time())
    collection.update_one({'reference': ref}, {'$set': {'status': 'Awaiting Student',
                                                         'staff_notes': [{'text': 'private-marker'}]}})
    assert b'private-marker' not in client.get(created.location).data
    assert client.post(created.location, data={'csrf_token': csrf, 'reply': 'My response'}).status_code == 302
    assert database.events.count_documents({'event_type': 'student_reply', 'case_reference': ref}) == 1
    assert 'My response' not in repr(database.events.find_one({'event_type': 'student_reply'}))


def test_staff_stale_updates_reassignment_and_audit(setup_cases):
    app, collection = setup_cases
    database = collection.database
    app.extensions['audit_writer'] = database.client
    app.config['MONGODB_AUDIT_DB'] = database.name
    student = User({'_id': ObjectId(), 'role': 'student'})
    first = User({'_id': ObjectId(), 'role': 'staff'})
    second = User({'_id': ObjectId(), 'role': 'staff'})
    database.users.insert_one({'_id': ObjectId(second.id), 'role': 'staff', 'is_active': True,
                               'full_name': 'Fictional Officer', 'email': 'officer@example.edu'})
    accounts = {user.id: user for user in (student, first, second)}
    app.login_manager.user_loader(lambda uid: accounts.get(uid))
    client = app.test_client()
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'Example', False)
        assert cases.claim_case(first, reference)
    with client.session_transaction() as session:
        session.update(_user_id=first.id, _fresh=True, last_activity=time.time())
    path = '/staff/cases/' + reference
    page = client.get(path).get_data(as_text=True)
    assert 'reassign-dialog' in page and 'archive-dialog' in page
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    assert 'name="version" value="1"' in page
    assert client.post(path, data={'action': 'archive', 'version': '1'}).status_code == 400
    status = {'csrf_token': csrf, 'version': '1', 'action': 'status', 'status': 'Awaiting Student'}
    assert client.post(path, data=status).status_code == 302
    assert client.post(path, data={'csrf_token': csrf, 'version': '1', 'action': 'note', 'note': 'Stale private note'}).status_code == 409
    assert not collection.find_one({'reference': reference}).get('staff_notes')
    event = database.events.find_one({'event_type': 'case_status'})
    assert event['old_value'] == 'Assigned' and event['new_value'] == 'Awaiting Student'
    data = {'csrf_token': csrf, 'version': '2', 'action': 'reassign', 'reassign': second.id}
    assert client.post(path, data={**data, 'reassign': first.id}).status_code == 400
    assert client.post(path, data={**data, 'reassign': 'not-an-object-id'}).status_code == 400
    assert client.post(path, data=data).status_code == 302
    event = database.events.find_one({'event_type': 'case_reassign'})
    assert event['old_value'] == first.id and event['new_value'] == second.id
    assert client.get(path).status_code == 404
    with client.session_transaction() as session:
        session.update(_user_id=second.id, _fresh=True, last_activity=time.time())
    assert client.get(path).status_code == 200
    assert client.post(path, data={'csrf_token': csrf, 'version': '3', 'action': 'archive'}).status_code == 302
    assert collection.find_one({'reference': reference})['archived'] is True
    with app.app_context():
        assert cases.get_student_case(student, reference) is None


def test_legacy_versions_and_student_reply_invalidate_staff_form(setup_cases):
    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'Example', False)
        collection.update_one({'reference': reference}, {'$unset': {'version': ''}, '$set': {'assigned_to': ObjectId(staff.id), 'status': 'Awaiting Student'}})
        assert cases.get_staff_case(staff, reference)['version'] == 0
        assert cases.add_student_reply(student, reference, 'Student response')
        assert cases.update_staff_case(staff, reference, 'status', 'Done', 0) is None
        assert cases.update_staff_case(staff, reference, 'status', 'Done', 1) is not None
        assert cases.update_staff_case(staff, reference, 'status', 'Awaiting Student', 2) is None
        assert collection.find_one({'reference': reference})['version'] == 2


def test_note_audit_records_only_counts(setup_cases):
    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    with app.app_context():
        ref = cases.create_student_case(student, 'Academic', 'Example', False)
        assert cases.claim_case(staff, ref)
        result = cases.update_staff_case(staff, ref, 'note', 'sensitive note marker', 1)
        assert result == {'old_value': 0, 'new_value': 1}
        assert 'sensitive note marker' not in repr(result)


def test_dashboard_context_never_receives_private_staff_notes(setup_cases):
    from flask import template_rendered

    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    accounts = {user.id: user for user in (student, staff)}
    app.login_manager.user_loader(lambda uid: accounts.get(uid))
    private_marker = 'private-note-context-test-marker'
    visible_marker = 'student-visible-context-test-marker'
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', visible_marker, False)
        assert cases.claim_case(staff, reference)
        assert cases.update_staff_case(staff, reference, 'note', private_marker, 1)
    assert private_marker not in repr(collection.find_one({'reference': reference}))

    rendered = []
    def capture(sender, template, context, **kwargs):
        rendered.append((template.name, dict(context)))

    client = app.test_client()
    with template_rendered.connected_to(capture, app):
        with client.session_transaction() as session:
            session.update(_user_id=staff.id, _fresh=True, last_activity=time.time())
        assert client.get('/staff/cases/' + reference).status_code == 200
        assert rendered[-1][0] == 'staff/detail.html'
        assert private_marker in repr(rendered[-1][1]['case'])

        with client.session_transaction() as session:
            session.update(_user_id=student.id, _fresh=True, last_activity=time.time())
        for path, template_name, context_key in [
            ('/student/home', 'student/home.html', 'cases'),
            ('/student/requests/' + reference, 'student/detail.html', 'case'),
        ]:
            response = client.get(path)
            assert response.status_code == 200
            assert rendered[-1][0] == template_name
            context = rendered[-1][1]
            assert all(private_marker not in repr(value) for value in context.values())
            assert 'staff_notes' not in repr(context[context_key])
            assert 'private_notes' not in repr(context[context_key])
        assert visible_marker in client.get('/student/requests/' + reference).get_data(as_text=True)


def test_dashboards_fail_safely_with_wrong_encryption_key(setup_cases):
    import json
    from cryptography.fernet import Fernet

    app, _ = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    accounts = {user.id: user for user in (student, staff)}
    app.login_manager.user_loader(lambda uid: accounts.get(uid))
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'Confidential test text', False)
        assert cases.claim_case(staff, reference)
    app.config['CASE_ENCRYPTION_KEYS'] = json.dumps({'test-v1': Fernet.generate_key().decode()})
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=student.id, _fresh=True, last_activity=time.time())
    for path in ('/student/home', '/student/requests/' + reference):
        response = client.get(path)
        assert response.status_code == 503
        assert b'Confidential test text' not in response.data
    with client.session_transaction() as session:
        session.update(_user_id=staff.id, _fresh=True, last_activity=time.time())
    response = client.get('/staff/cases/' + reference)
    assert response.status_code == 503
    assert b'Confidential test text' not in response.data


def test_operator_inputs_cannot_change_case_queries(setup_cases):
    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    operator = {'$ne': ''}
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'Fictional request', False)
        for category, description, urgent in [(operator, 'text', False),
                                               ('Academic', operator, False),
                                               ('Academic', 'text', operator)]:
            with pytest.raises(ValueError):
                cases.create_student_case(student, category, description, urgent)
        assert cases.get_student_case(student, operator) is None
        assert not cases.add_student_reply(student, operator, 'text')
        assert not cases.claim_case(staff, operator)
        assert cases.get_staff_case(staff, operator) is None
        assert cases.claim_case(staff, reference)
        assert cases.update_staff_case(staff, operator, 'note', 'text', 1) is None
        with pytest.raises(ValueError):
            cases.update_staff_case(staff, reference, 'reassign', operator, 1)
        with pytest.raises(ValueError):
            cases.update_staff_case(staff, reference, 'status', operator, 1)
        assert collection.count_documents({}) == 1
        assert collection.find_one({'reference': reference})['version'] == 1


def test_unassigned_queue_exposes_metadata_but_not_case_detail(setup_cases):
    app, _ = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    app.login_manager.user_loader(lambda uid: staff if uid == staff.id else None)
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'unassigned-private-marker', False)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=staff.id, _fresh=True, last_activity=time.time())
    response = client.get('/staff/home')
    assert response.status_code == 200
    assert reference.encode() in response.data
    assert b'unassigned-private-marker' not in response.data
    assert client.get('/staff/cases/' + reference).status_code == 404


def test_all_staff_changes_write_content_free_audit_events(setup_cases):
    app, collection = setup_cases
    database = collection.database
    app.extensions['audit_writer'] = database.client
    app.config['MONGODB_AUDIT_DB'] = database.name
    student = User({'_id': ObjectId(), 'role': 'student'})
    first = User({'_id': ObjectId(), 'role': 'staff'})
    second = User({'_id': ObjectId(), 'role': 'staff'})
    database.users.insert_one({'_id': ObjectId(second.id), 'role': 'staff', 'is_active': True})
    accounts = {user.id: user for user in (student, first, second)}
    app.login_manager.user_loader(lambda uid: accounts.get(uid))
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'private description marker', False)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(_user_id=first.id, _fresh=True, last_activity=time.time())
    queue = client.get('/staff/home').get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', queue).group(1)
    path = '/staff/cases/' + reference
    assert client.post(path + '/claim', data={'csrf_token': csrf}).status_code == 302
    actions = [(1, 'note', 'private note marker'), (2, 'message', 'student message marker'),
               (3, 'status', 'Awaiting Student'), (4, 'reassign', second.id)]
    for version, action, value in actions:
        assert client.post(path, data={'csrf_token': csrf, 'version': str(version),
                                       'action': action, action: value}).status_code == 302
    with client.session_transaction() as session:
        session.update(_user_id=second.id, _fresh=True, last_activity=time.time())
    assert client.post(path, data={'csrf_token': csrf, 'version': '5', 'action': 'archive'}).status_code == 302
    events = list(database.events.find({'case_reference': reference}))
    event_types = {event['event_type'] for event in events}
    assert {'case_claimed', 'case_status', 'case_note', 'case_message', 'case_reassign', 'case_archive'} <= event_types
    assert any(event['event_type'] == 'case_status' and event['old_value'] == 'New'
               and event['new_value'] == 'Assigned' for event in events)
    for event in events:
        assert 'old_value' in event and 'new_value' in event
        for secret in ('private description marker', 'private note marker', 'student message marker'):
            assert secret not in repr(event)


def test_legacy_received_case_remains_claimable(setup_cases):
    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'Legacy example', False)
        collection.update_one({'reference': reference}, {'$set': {'status': 'Received'}})
        assert cases.claim_case(staff, reference, include_previous=True) == 'Received'
        assert cases.get_staff_case(staff, reference)['status'] == 'Assigned'


def test_mongosh_raw_case_has_no_plaintext(setup_cases):
    import json
    import subprocess

    if os.environ.get('RUN_MONGOSH_TESTS') != '1':
        pytest.skip('Set RUN_MONGOSH_TESTS=1 to inspect a disposable case through Docker mongosh.')
    app, collection = setup_cases
    student = User({'_id': ObjectId(), 'role': 'student'})
    staff = User({'_id': ObjectId(), 'role': 'staff'})
    with app.app_context():
        reference = cases.create_student_case(student, 'Academic', 'mongo-description-test-marker', False)
        assert cases.claim_case(staff, reference)
        assert cases.update_staff_case(staff, reference, 'note', 'mongo-note-test-marker', 1)
    # Credentials are read inside the container and never placed in command arguments.
    script = ('if (!db.getSiblingDB("admin").auth(process.env.MONGO_INITDB_ROOT_USERNAME, '
              'process.env.MONGO_INITDB_ROOT_PASSWORD)) throw Error("authentication failed"); '
              'const record = db.getSiblingDB(' + json.dumps(collection.database.name) + ').cases.findOne({reference: '
              + json.dumps(reference) + '}); if (!record) throw Error("case missing"); '
              'const raw = EJSON.stringify(record); '
              'if (raw.includes("mongo-description-test-marker") || raw.includes("mongo-note-test-marker")) '
              'throw Error("plaintext detected"); print("encrypted case verified");')
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'mongodb', 'mongosh', '--quiet', '--norc',
                             '--eval', script], capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, 'mongosh inspection failed'
    assert 'encrypted case verified' in result.stdout
