from datetime import datetime, timezone
from bson import ObjectId
import pytest
from scripts.seed_cases import BATCH, DESCRIPTIONS, STATUSES, build_cases, insert_cases
from services.cases import CATEGORIES, _view


def test_demo_cases_match_application_schema_and_are_fictional():
    now = datetime.now(timezone.utc)
    student, staff = ObjectId(), ObjectId()
    cases = build_cases([student], [staff], 180, now)
    assert len(cases) == 180 and len({case['_id'] for case in cases}) == 180
    assert set(case['category'] for case in cases) == set(CATEGORIES)
    assert set(case['status'] for case in cases) == set(STATUSES)
    assert all(len(texts) >= 5 for texts in DESCRIPTIONS.values())
    for case in cases:
        assert case['owner_id'] == student and case['created_at'] <= case['updated_at'] <= now
        assert case['demo_seed_batch'] == BATCH
        assert len(case['reference']) == 32
        assert case['student_updates'][0]['text'].removeprefix('Fictional demo: ') in DESCRIPTIONS[case['category']]
        assert 'staff_notes' not in _view(case) and _view(case)['summary'] == 'Fictional demo request.'
        if case['status'] == 'Received':
            assert case['assigned_to'] is None and 'staff_notes' not in case
        else:
            assert case['assigned_to'] == staff and case['staff_notes']


def test_seed_rejects_invalid_inputs_and_existing_batch():
    with pytest.raises(ValueError):
        build_cases([], [ObjectId()])
    with pytest.raises(ValueError):
        build_cases([ObjectId()], [ObjectId()], 149)
    class Existing:
        def count_documents(self, query, limit): return 1
        def insert_many(self, *args, **kwargs): pytest.fail('must not overwrite')
    with pytest.raises(ValueError, match='already exists'):
        insert_cases(Existing(), build_cases([ObjectId()], [ObjectId()]))


def test_seeded_cases_work_with_real_case_services():
    import os
    import uuid
    from types import SimpleNamespace
    from unittest.mock import patch
    from pymongo import MongoClient
    from scripts.seed_cases import demo_account_ids
    from services.cases import get_student_cases, staff_queue, get_staff_case
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('TEST_MONGODB_URI required for isolated MongoDB test.')
    client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=3000)
    name = 'unidays_test_' + uuid.uuid4().hex
    database = client[name]
    student, staff, other = ObjectId(), ObjectId(), ObjectId()
    try:
        database.users.insert_many([
            {'_id': student, 'role': 'student', 'is_demo': True, 'is_active': True},
            {'_id': staff, 'role': 'staff', 'is_demo': True, 'is_active': True},
            {'_id': other, 'role': 'staff', 'is_active': True},
        ])
        students = demo_account_ids(database.users, 'student')
        officers = demo_account_ids(database.users, 'staff')
        assert students == [student] and officers == [staff]
        assert demo_account_ids(database.users, 'student', use_existing=True) == [student]
        with pytest.raises(ValueError, match='exactly one active staff'):
            demo_account_ids(database.users, 'staff', use_existing=True)
        insert_cases(database.cases, build_cases(students, officers))
        student_user = SimpleNamespace(id=str(student), role='student', is_authenticated=True)
        staff_user = SimpleNamespace(id=str(staff), role='staff', is_authenticated=True)
        with patch('db.get_cases', return_value=database.cases):
            student_cases = get_student_cases(student_user)
            queue = staff_queue(staff_user)
            assigned = next(case for case in queue if case['claimed'])
            staff_case = get_staff_case(staff_user, assigned['reference'])
        assert len(student_cases) == 180 and len(queue) == 180
        assert staff_case['private_notes'] and 'Fictional note' not in repr(student_cases)
        with pytest.raises(ValueError, match='already exists'):
            insert_cases(database.cases, build_cases(students, officers))
        assert database.cases.count_documents({}) == 180
    finally:
        client.drop_database(name)
        client.close()
