"""Synthetic dashboard data only; never a substitute for authorization.

The eventual database services must enforce role and object-level access before
returning data. These separate projections keep staff notes out of student and
admin template contexts, even during the UI prototype.
"""

from copy import deepcopy


def _require_role(user, role):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'role', None) != role:
        raise PermissionError('This mock view is not available for this role.')


def get_student_cases(user):
    _require_role(user, 'student')
    # All examples are invented. Real queries must restrict by the student's ID.
    return deepcopy([
        {'reference': 'REQ-1042', 'category_label': 'Personal support', 'status': 'In progress',
         'summary': 'A member of the team is looking at your request.', 'updated': 'Today',
         'progress': 2, 'timeline': [{'when': 'Today', 'text': 'A support team member is looking into your request.'},
                                    {'when': 'Yesterday', 'text': 'We received your request.'}]},
        {'reference': 'REQ-1031', 'category_label': 'Study support', 'status': 'Awaiting Student',
         'summary': 'The team has asked for a little more information.', 'updated': 'Yesterday', 'progress': 3,
         'timeline': [{'when': 'Yesterday', 'text': 'The team has asked you to reply when you can.'},
                      {'when': 'Earlier', 'text': 'We received your request.'}]},
    ])


def get_student_case(user, reference):
    # Synthetic fixtures only. Real storage must filter by both case ID and owner.
    return next((case for case in get_student_cases(user) if case['reference'] == reference), None)


def get_staff_queue(user):
    _require_role(user, 'staff')
    # Future implementation must check staff assignment and permissions per case.
    return deepcopy([
        {'reference': 'REQ-1042', 'category_label': 'Personal support', 'status': 'New',
         'student_name': 'Alex Example', 'updated': 'Today', 'age_days': 1, 'attention': 'New request',
         'assigned_to': 'You', 'conversation': [{'by': 'Student', 'when': 'Today', 'text': 'I would like to talk through my options.'}],
         'private_notes': 'Fictional internal note.'},
        {'reference': 'REQ-1031', 'category_label': 'Study support', 'status': 'Awaiting Student',
         'student_name': 'Sam Sample', 'updated': '4 days ago', 'age_days': 4, 'attention': 'Waiting for a reply',
         'assigned_to': 'You', 'conversation': [{'by': 'Support team', 'when': '4 days ago', 'text': 'Please reply whenever you are ready.'}],
         'private_notes': 'Example only: check in if there is no response.'},
        {'reference': 'REQ-1023', 'category_label': 'Practical support', 'status': 'In progress',
         'student_name': 'Taylor Example', 'updated': '6 days ago', 'age_days': 6, 'attention': 'Older request',
         'assigned_to': 'You', 'conversation': [{'by': 'Student', 'when': '6 days ago', 'text': 'I could use some guidance.'}],
         'private_notes': 'Example only: follow up with the team.'},
    ])


def get_staff_case(user, reference):
    # Real records must be scoped to the officer's assignment on every request.
    return next((case for case in get_staff_queue(user) if case['reference'] == reference), None)


def get_admin_overview(user):
    _require_role(user, 'admin')
    # Aggregates only: no case descriptions, conversations or private notes.
    return deepcopy({'open_requests': 12, 'awaiting_reply': 3,
                     'categories': [{'label': 'Personal support', 'count': 5},
                                    {'label': 'Study support', 'count': 7}]})


def get_admin_users(user):
    _require_role(user, 'admin')
    # Invented identities only; real user management needs separate authorization.
    return deepcopy([
        {'reference': 'USR-1001', 'name': 'Alex Example', 'role': 'student', 'active': True},
        {'reference': 'USR-1002', 'name': 'Sam Sample', 'role': 'staff', 'active': True},
        {'reference': 'USR-1003', 'name': 'Taylor Example', 'role': 'student', 'active': False},
    ])


def get_admin_events(user):
    _require_role(user, 'admin')
    # No case content or sensitive category is exposed in audit fixtures.
    return deepcopy([
        {'type': 'Sign-in', 'actor': 'Sam Sample', 'action': 'signed in', 'when': 'Today, 09:15', 'source': 'Local demo'},
        {'type': 'Account', 'actor': 'Support administrator', 'action': 'created a staff account', 'when': 'Yesterday, 15:40', 'source': 'Local demo'},
        {'type': 'Access', 'actor': 'An account', 'action': 'was denied access to a restricted page', 'when': 'Yesterday, 11:30', 'source': 'Local demo'},
    ])
