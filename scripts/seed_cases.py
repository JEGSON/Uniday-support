"""Create local-only fictional support cases for demo or explicitly selected existing accounts.

The default is a dry run. No registry or real-user data is imported, and no
existing case is updated or deleted. See --help for account prerequisites.
"""
import argparse
import hashlib
import random
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo.errors import PyMongoError

from app import create_app
import db
from services.case_crypto import encrypt_text

BATCH = 'fictional-cases-v1'
DESCRIPTIONS = {
    'Academic': [
        'I would like to talk through my study schedule.',
        'Could someone help me understand the coursework process?',
        'I am looking for guidance on managing deadlines.',
        'I would like to discuss options for study support.',
        'Can I get help planning my next term?',
    ],
    'Financial': [
        'I would appreciate guidance on budgeting for the term.',
        'Could someone explain what financial support is available?',
        'I would like help understanding the funding process.',
        'Can we discuss options for managing course-related costs?',
        'I have a question about applying for student support funding.',
    ],
    'Wellbeing': [
        'I would like to speak with someone about settling into university.',
        'Could someone tell me about wellbeing support options?',
        'I would appreciate a conversation about my routine.',
        'I would like help finding the right support contact.',
        'Can someone explain how to arrange a wellbeing appointment?',
    ],
    'Disability': [
        'I would like information about accessible study materials.',
        'Could someone explain how to discuss access arrangements?',
        'I have a question about accessibility support for classes.',
        'Can we discuss available learning adjustments?',
        'I would like guidance on contacting the accessibility team.',
    ],
    'Accommodation': [
        'I would like to discuss my university housing options.',
        'Could someone explain where to ask a housing question?',
        'I need guidance on the accommodation application process.',
        'Can we talk about support with a housing enquiry?',
        'I would like to know who can help with a tenancy question.',
    ],
    'Something else': [
        'I am unsure which team to contact for my question.',
        'Could someone point me towards the right support service?',
        'I would like to ask about a general student matter.',
        'Can someone help me understand the next step?',
        'I have a general question about student services.',
    ],
}
NOTES = [
    'Fictional note: review the appropriate support guidance.',
    'Fictional note: consider a follow-up when appropriate.',
    'Fictional note: check the relevant service information.',
    'Fictional note: prepare a short response for the student.',
    'Fictional note: confirm the next appropriate step.',
]
# App values: New -> Received, In Progress -> In progress, Closed -> Done.
STATUSES = ('Received', 'In progress', 'Awaiting Student', 'Done')


def build_cases(student_ids, staff_ids, count=180, now=None):
    if not 150 <= count <= 300:
        raise ValueError('Choose between 150 and 300 cases.')
    if not student_ids or not staff_ids or any(not isinstance(x, ObjectId) for x in student_ids + staff_ids):
        raise ValueError('Demo student and staff account IDs are required.')
    now = now or datetime.now(timezone.utc)
    rng = random.Random(697)  # Demo fixtures only; never used for security tokens.
    categories = tuple(DESCRIPTIONS)
    records = []
    for index in range(count):
        category = categories[index % len(categories)]
        status = STATUSES[(index // len(categories)) % len(STATUSES)]
        created = now - timedelta(days=rng.randint(2, 180), hours=rng.randint(0, 23))
        updated = created + timedelta(seconds=rng.randint(0, int((now - created).total_seconds())))
        digest = hashlib.sha256(f'{BATCH}:{index}'.encode()).hexdigest()
        student = student_ids[index % len(student_ids)]
        # New cases are intentionally unassigned so the real claim flow can be tested.
        staff = None if status == 'Received' else staff_ids[(index // len(categories)) % len(staff_ids)]
        record = {'_id': ObjectId(digest[:24]), 'reference': secrets.token_hex(16), 'demo_seed_batch': BATCH,
                  'owner_id': student, 'category': category, 'status': status, 'version': 0, 'urgent': False,
                  'created_at': created, 'updated_at': updated, 'assigned_to': staff,
                  'student_updates': [{'at': created, 'by': 'Student',
                                       'text': 'Fictional demo: ' + rng.choice(DESCRIPTIONS[category])}]}
        if staff is not None:
            record['staff_notes'] = [{'at': updated, 'text': rng.choice(NOTES)}]
        records.append(record)
    return records


def demo_account_ids(users, role, use_existing=False):
    # Existing accounts are only selected with explicit consent and no ambiguity.
    query = {'role': role, 'is_active': True}
    if not use_existing:
        query['is_demo'] = True
    ids = [row['_id'] for row in users.find(query, {'_id': 1})]
    if use_existing and len(ids) != 1:
        raise ValueError(f'Expected exactly one active {role} account; found {len(ids)}. No cases were written.')
    return ids


def insert_cases(collection, records):
    # Fixed _ids make duplicate batches fail even if two seeders race; never replace existing cases.
    if collection.count_documents({'demo_seed_batch': BATCH}, limit=1):
        raise ValueError('This demo batch already exists. Existing cases were not changed.')
    encrypted = []
    for record in records:
        document = dict(record)
        for field in ('student_updates', 'staff_notes'):
            if field in document:
                document[field] = [dict(item, text=encrypt_text(item['text'], document['reference'], field))
                                   for item in document[field]]
        encrypted.append(document)
    collection.insert_many(encrypted, ordered=True)


def main():
    parser = argparse.ArgumentParser(description='Prepare fictional case fixtures for local demo accounts.')
    parser.add_argument('--count', type=int, default=180, help='Number of cases, between 150 and 300 (default: 180).')
    parser.add_argument('--use-existing-accounts', action='store_true',
                        help='Use the sole active student and sole active staff account, only when explicitly requested.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Write cases for active, explicitly marked demo accounts.')
    mode.add_argument('--dry-run', action='store_true', help='Generate in memory only (default).')
    args = parser.parse_args()
    try:
        if not args.apply:
            cases = build_cases([ObjectId()], [ObjectId()], args.count)
            print(f'Dry run: {len(cases)} fictional cases prepared in memory; nothing was written.')
            return
        app = create_app()
        with app.app_context():
            users = db.get_users()
            students = demo_account_ids(users, 'student', use_existing=args.use_existing_accounts)
            staff = demo_account_ids(users, 'staff', use_existing=args.use_existing_accounts)
            if not students or not staff:
                raise ValueError('Active accounts marked is_demo=true are required for both student and staff. No cases were written.')
            cases = build_cases(students, staff, args.count)
            insert_cases(db.get_cases(), cases)
        print(f'Inserted {len(cases)} fictional cases for the selected local accounts.')
    except (ValueError, PyMongoError, RuntimeError) as exc:
        # Database exception details can include credentials; do not log them.
        if isinstance(exc, ValueError):
            parser.exit(1, f'Case seeding failed: {exc}\n')
        parser.exit(1, 'Case seeding failed because the database is unavailable or the batch conflicts. '
                       'An interrupted insertion may be partial; inspect before retrying.\n')


if __name__ == '__main__':
    main()
