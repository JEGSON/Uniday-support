import json

import pytest

from scripts.seed_registry import load_records
from services.registry import validate_record


def test_registry_normalizes_records_and_starts_unclaimed():
    record = validate_record({'student_id': ' demo-1 ', 'full_name': 'Example Student',
                              'course': 'Computing', 'university_email': 'Student@Example.edu'})
    assert record['student_id'] == 'DEMO-1'
    assert record['university_email'] == 'student@example.edu'
    assert record['claimed'] is False and record['claimed_by_user_id'] is None


def test_registry_rejects_operator_and_extra_fields():
    with pytest.raises(ValueError):
        validate_record({'student_id': {'$ne': ''}, 'full_name': 'Example Student',
                         'course': 'Computing', 'university_email': 'x@example.edu'})
    with pytest.raises(ValueError):
        validate_record({'student_id': 'A', 'full_name': 'Example Student', 'course': 'Computing',
                         'university_email': 'x@example.edu', 'claimed': True})


def test_import_rejects_normalized_duplicates(tmp_path):
    path = tmp_path / 'records.json'
    one = {'student_id': 'abc', 'full_name': 'Example Student', 'course': 'Computing',
           'university_email': 'x@example.edu'}
    path.write_text(json.dumps([one, dict(one, student_id='ABC', university_email='y@example.edu')]))
    with pytest.raises(ValueError):
        load_records(path)


def test_import_preserves_claims_and_rejects_conflicts():
    import os
    import uuid
    from pymongo import MongoClient
    from scripts.seed_registry import import_records
    uri = os.environ.get('TEST_MONGODB_URI')
    if not uri:
        pytest.skip('TEST_MONGODB_URI required for isolated registry test.')
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    name = 'unidays_test_' + uuid.uuid4().hex
    collection = client[name].student_registry
    record = validate_record({'student_id': 'UCI000001', 'full_name': 'Example Student',
                              'course': 'Computing', 'university_email': 'uci000001@students.example.ac.uk'})
    try:
        assert import_records(collection, [record]) == (1, 0)
        collection.update_one({'student_id': record['student_id']}, {'$set': {'claimed': True, 'claimed_by_user_id': 'test-owner'}})
        assert import_records(collection, [record]) == (0, 1)
        stored = collection.find_one({'student_id': record['student_id']})
        assert stored['claimed'] is True and stored['claimed_by_user_id'] == 'test-owner'
        conflict = dict(record, full_name='Different Name')
        new = validate_record({'student_id': 'UCI000002', 'full_name': 'Another Student',
                               'course': 'Computing', 'university_email': 'uci000002@students.example.ac.uk'})
        with pytest.raises(ValueError, match='conflicts'):
            import_records(collection, [new, conflict])
        assert collection.count_documents({}) == 1
    finally:
        client.drop_database(name)
        client.close()
