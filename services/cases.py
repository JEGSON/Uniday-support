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
TRANSITIONS = {'Assigned': ('In progress', 'Awaiting Student', 'Done'),
               'In progress': ('Awaiting Student', 'Done'),
               'Awaiting Student': ('In progress', 'Done'),
               'Done': ('In progress',)}
# Database projection excludes private notes before records reach the student service.
_STUDENT_FIELDS = {'_id': 0, 'reference': 1, 'category': 1, 'status': 1,
                   'updated_at': 1, 'student_updates': 1, 'demo_seed_batch': 1}


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
            'status': status, 'summary': 'Fictional demo request.' if document.get('demo_seed_batch') else 'Your request has been saved.',
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
                               'status': 'Received', 'version': 0, 'urgent': urgent, 'created_at': now, 'updated_at': now,
                               'student_updates': [{'at': now, 'text': description.strip()}]})
    return reference


def get_student_cases(user):
    owner = _owner(user)
    # Owner filter is mandatory regardless of what reference a client supplies.
    return [_view(case) for case in db.get_cases().find({'owner_id': owner, 'archived': {'$ne': True}}, _STUDENT_FIELDS).sort('created_at', -1)]


def get_student_case(user, reference):
    owner = _owner(user)
    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        return None
    case = db.get_cases().find_one({'owner_id': owner, 'reference': reference, 'archived': {'$ne': True}}, _STUDENT_FIELDS)
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
        {'owner_id': owner, 'reference': reference, 'status': 'Awaiting Student', 'archived': {'$ne': True}},
        {'$push': {'student_updates': {'at': now, 'text': reply.strip()}},
         '$set': {'updated_at': now, 'status': 'In progress'}, '$inc': {'version': 1}}, return_document=ReturnDocument.AFTER)
    return result is not None


def _staff(user):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'role', None) != 'staff':
        raise PermissionError('Staff access required.')
    if not isinstance(user.id, str) or not ObjectId.is_valid(user.id):
        raise ValueError('Invalid account identifier.')
    return ObjectId(user.id)


def _reference_ok(reference):
    return isinstance(reference, str) and _REFERENCE.fullmatch(reference) is not None


def _queue_view(document):
    # The unassigned queue deliberately excludes case descriptions and private notes.
    now = datetime.now(timezone.utc)
    created = document['created_at']
    return {'reference': document['reference'], 'category_label': _LABELS[document['category']],
            'status': document['status'], 'student_name': 'Student request',
            'updated': document['updated_at'].strftime('%d %b %Y'),
            'age_days': max(0, (now - created).days),
            'attention': ('Fictional demo request' if document.get('demo_seed_batch') else
                          ('Marked urgent' if document.get('urgent') else 'Request')),
            'is_demo': bool(document.get('demo_seed_batch')),
            'claimed': document.get('assigned_to') is not None}


def staff_queue(user, assigned_only=False):
    staff_id = _staff(user)
    query = {'assigned_to': staff_id} if assigned_only else {'$or': [{'assigned_to': None}, {'assigned_to': staff_id}]}
    query['archived'] = {'$ne': True}
    fields = {'reference': 1, 'category': 1, 'status': 1, 'updated_at': 1,
              'created_at': 1, 'urgent': 1, 'assigned_to': 1, 'demo_seed_batch': 1}
    return [_queue_view(case) for case in db.get_cases().find(query, fields)]


def claim_case(user, reference):
    staff_id = _staff(user)
    if not _reference_ok(reference):
        return False
    now = datetime.now(timezone.utc)
    # A single conditional write ensures concurrent staff cannot both claim a case.
    result = db.get_cases().find_one_and_update(
        {'reference': reference, 'assigned_to': None, 'status': 'Received', 'archived': {'$ne': True}},
        {'$set': {'assigned_to': staff_id, 'status': 'Assigned', 'updated_at': now}, '$inc': {'version': 1}},
        return_document=ReturnDocument.AFTER)
    return result is not None


def get_staff_case(user, reference):
    staff_id = _staff(user)
    if not _reference_ok(reference):
        return None
    document = db.get_cases().find_one({'reference': reference, 'assigned_to': staff_id, 'archived': {'$ne': True}})
    if not document:
        return None
    case = _queue_view(document)
    case['version'] = document.get('version', 0)
    case['allowed_statuses'] = TRANSITIONS.get(document['status'], ())
    case['conversation'] = [{'by': item.get('by', 'Student'), 'when': item['at'].strftime('%d %b %Y, %H:%M UTC'),
                             'text': item['text']} for item in document.get('student_updates', [])]
    case['private_notes'] = [{'when': item['at'].strftime('%d %b %Y, %H:%M UTC'), 'text': item['text']}
                             for item in document.get('staff_notes', [])]
    return case


def active_staff_choices(user):
    staff_id = _staff(user)
    return [{'id': str(doc['_id']), 'name': doc.get('full_name', 'Support officer')}
            for doc in db.get_users().find({'role': 'staff', 'is_active': True, '_id': {'$ne': staff_id}},
                                           {'full_name': 1}).sort('full_name', 1).limit(100)]


def update_staff_case(user, reference, action, value='', expected_version=None):
    staff_id = _staff(user)
    if not _reference_ok(reference):
        return None
    if type(expected_version) is not int or not 0 <= expected_version <= 2**31 - 1:
        raise ValueError('Invalid case version.')
    now = datetime.now(timezone.utc)
    update = {'$set': {'updated_at': now}, '$inc': {'version': 1}}
    query = {'reference': reference, 'assigned_to': staff_id, 'archived': {'$ne': True}}
    query['$or'] = [{'version': 0}, {'version': {'$exists': False}}] if expected_version == 0 else [{'version': expected_version}]
    if action == 'status' and isinstance(value, str) and value in ('In progress', 'Awaiting Student', 'Done'):
        # MongoDB checks the previous state together with assignment and version.
        query['status'] = {'$in': [source for source, destinations in TRANSITIONS.items() if value in destinations]}
        update['$set']['status'] = value
    elif action in ('note', 'message') and isinstance(value, str) and value.strip() and len(value) <= 3000:
        item = {'at': now, 'text': value.strip()}
        if action == 'message':
            item['by'] = 'Support team'
        update['$push'] = {'staff_notes' if action == 'note' else 'student_updates': item}
    elif action == 'archive':
        update['$set']['archived'] = True
    elif action == 'reassign' and isinstance(value, str) and ObjectId.is_valid(value):
        target = ObjectId(value)
        if target == staff_id or not db.get_users().find_one({'_id': target, 'role': 'staff', 'is_active': True}, {'_id': 1}):
            raise ValueError('Invalid assignee.')
        update['$set']['assigned_to'] = target
    else:
        raise ValueError('Invalid case action.')
    # Use a conditional write so stale forms cannot overwrite newer changes.
    previous = db.get_cases().find_one_and_update(query, update, return_document=ReturnDocument.BEFORE)
    if previous is None:
        return None
    if action == 'status':
        return {'old_value': previous['status'], 'new_value': value}
    if action == 'reassign':
        return {'old_value': str(staff_id), 'new_value': value}
    if action == 'archive':
        return {'old_value': False, 'new_value': True}
    # Record only counts for appended notes/messages, never sensitive text.
    field = 'staff_notes' if action == 'note' else 'student_updates'
    previous_count = len(previous.get(field, []))
    return {'old_value': previous_count, 'new_value': previous_count + 1}
