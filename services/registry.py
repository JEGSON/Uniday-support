"""Validation and indexing for the trusted student registry."""

from services.users import validate_signup


def validate_record(record):
    """Accept only the expected scalar fields before a MongoDB operation."""
    if not isinstance(record, dict):
        raise ValueError('Each registry entry must be an object.')
    fields = ('student_id', 'full_name', 'course', 'university_email')
    if set(record) != set(fields) or any(not isinstance(record[k], str) for k in fields):
        raise ValueError('Registry entries must contain exactly the four text fields.')
    sample = {'student_id': record['student_id'], 'full_name': record['full_name'],
              'course': record['course'], 'email': record['university_email'],
              'password': 'registry-validation-placeholder', 'confirm_password': 'registry-validation-placeholder'}
    values, errors = validate_signup(sample)
    if errors:
        raise ValueError('Registry entry contains invalid fields.')
    return {'student_id': values['student_id'], 'full_name': values['full_name'],
            'course': values['course'], 'university_email': values['email'],
            'claimed': False, 'claimed_at': None, 'claimed_by_user_id': None}


def ensure_indexes(collection):
    collection.create_index('student_id', name='registry_student_id_unique', unique=True)
    collection.create_index('university_email', name='registry_email_unique', unique=True)
