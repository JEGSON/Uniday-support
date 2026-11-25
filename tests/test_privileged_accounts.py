from unittest.mock import Mock, patch

import pytest

from services.passwords import verify_password
from services.users import create_privileged_user


def details():
    return {'full_name': 'Test Staff', 'staff_id': 'staff-123', 'email': 'Staff@Example.com',
            'password': 'a unique long passphrase', 'confirm_password': 'a unique long passphrase'}


@pytest.mark.parametrize('role', ['staff', 'admin'])
def test_privileged_account_is_inactive_by_default(role):
    users = Mock()
    with patch('db.get_users', return_value=users):
        create_privileged_user(details(), role)
    record = users.insert_one.call_args.args[0]
    assert record['role'] == role and record['is_active'] is False
    assert record['staff_id'] == 'STAFF-123' and record['email'] == 'staff@example.com'
    assert 'student_id' not in record and 'course' not in record and 'password' not in record
    assert verify_password(record['password_hash'], details()['password'])


def test_only_allowed_roles_and_valid_inputs_are_inserted():
    users = Mock()
    bad = details()
    bad['staff_id'] = {'$ne': ''}
    with patch('db.get_users', return_value=users):
        with pytest.raises(ValueError):
            create_privileged_user(details(), 'student')
        with pytest.raises(ValueError):
            create_privileged_user(bad, 'admin')
        users.insert_one.assert_not_called()


def test_activation_is_explicit():
    users = Mock()
    with patch('db.get_users', return_value=users):
        create_privileged_user(details(), 'admin', activate=True)
    assert users.insert_one.call_args.args[0]['is_active'] is True


def test_validation_reports_password_issue_without_exposing_secret():
    data = details()
    data['password'] = data['confirm_password'] = 'shortsecret'
    with patch('db.get_users') as users, pytest.raises(ValueError) as error:
        create_privileged_user(data, 'staff')
    assert '15 and 128' in str(error.value)
    assert 'shortsecret' not in str(error.value)
    users.assert_not_called()
