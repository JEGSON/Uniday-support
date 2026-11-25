"""Student case storage; all reads and writes are scoped to the owner."""
import re
import secrets
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

import db

CATEGORIES = ('Wellbeing', 'Academic', 'Financial', 'Disability', 'Accommodation', 'Something else')
_LABELS = {'Wellbeing': 'Personal support', 'Disability': 'Personal support',
           'Academic': 'Study support', 'Financial': 'Practical support',
           'Accommodation': 'Practical support', 'Something else': 'Other support'}
_REFERENCE = re.compile(r'^[0-9a-f]{32}$')


def _owner(user):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'role', None) != 'student':
        raise PermissionError('Student access required.')
    if not isinstance(user.id, str) or not ObjectId.is_valid(user.id):
        raise ValueError('Invalid account identifier.')
    return ObjectId(user.id)


def _view(document):
    # Explicit allowlist: internal notes or future staff-only fields never enter templates.
    status = document['status']
    steps = {'Received': 0, 'Assigned': 1, 'In progress': 2, 'Awaiting Student': 3, 'Done': 4}
    return {'reference': document['reference'], 'category_label': _LABELS[document['category']],
            'status': status, 'summary': 'Your request has been saved.',
            'updated': document['updated_at'].strftime('%d %b %Y'), 'progress': steps.get(status, 0),
            'timeline': [{'when': item['at'].strftime('%d %b %Y, %H:%M UTC'), 'text': item['text']}
                         for item in document.get('student_updates', [])]}


def create_student_case(user, category, description, urgent):
    owner = _owner(user)
    if not isinstance(category, str) or category not in CATEGORIES:
        raise ValueError('Invalid category.')
    if not isinstance(description, str) or not description.strip() or len(description) > 3000:
        raise ValueError('Invalid description.')
    if not isinstance(urgent, bool):
        raise ValueError('Invalid urgent flag.')
    now = datetime.now(timezone.utc)
    reference = secrets.token_hex(16)
    db.get_cases().insert_one({'reference': reference, 'owner_id': owner, 'category': category,
                               'status': 'Received', 'urgent': urgent, 'created_at': now, 'updated_at': now,
                               'student_updates': [{'at': now, 'text': description.strip()}]})
    return reference


def get_student_cases(user):
    owner = _owner(user)
    # Owner filter is mandatory regardless of what reference a client supplies.
    return [_view(case) for case in db.get_cases().find({'owner_id': owner}).sort('created_at', -1)]


def get_student_case(user, reference):
    owner = _owner(user)
    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        return None
    case = db.get_cases().find_one({'owner_id': owner, 'reference': reference})
    return _view(case) if case else None


def add_student_reply(user, reference, reply):
    owner = _owner(user)
    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        return False
    if not isinstance(reply, str) or not reply.strip() or len(reply) > 3000:
        raise ValueError('Invalid reply.')
    now = datetime.now(timezone.utc)
    # Atomic filter prevents a reply if ownership or the status changed meanwhile.
    result = db.get_cases().find_one_and_update(
        {'owner_id': owner, 'reference': reference, 'status': 'Awaiting Student'},
        {'$push': {'student_updates': {'at': now, 'text': reply.strip()}},
         '$set': {'updated_at': now, 'status': 'In progress'}}, return_document=ReturnDocument.AFTER)
    return result is not None
