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
