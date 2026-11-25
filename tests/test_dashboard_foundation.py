from types import SimpleNamespace

import pytest

import mock_data


def user(role):
    return SimpleNamespace(role=role, is_authenticated=True)


def test_student_projection_has_no_private_notes():
    cases = mock_data.get_student_cases(user('student'))
    assert cases and all('private_notes' not in case for case in cases)
    assert 'Fictional internal note.' not in repr(cases)


def test_admin_projection_contains_only_aggregates():
    overview = mock_data.get_admin_overview(user('admin'))
    assert set(overview) == {'open_requests', 'awaiting_reply', 'categories'}
    assert 'private_notes' not in repr(overview) and 'description' not in repr(overview)


@pytest.mark.parametrize('role', ['student', 'staff', 'admin'])
def test_mock_services_refuse_other_roles(role):
    services = {'student': mock_data.get_student_cases, 'staff': mock_data.get_staff_queue,
                'admin': mock_data.get_admin_overview}
    for required, service in services.items():
        if required != role:
            with pytest.raises(PermissionError):
                service(user(role))


def test_mock_data_does_not_persist_changes():
    first = mock_data.get_student_cases(user('student'))
    first[0]['summary'] = 'modified'
    assert mock_data.get_student_cases(user('student'))[0]['summary'] != 'modified'
