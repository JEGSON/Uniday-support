"""Validate a CSV/JSON registry; use --apply to insert after reviewing a dry run."""

import argparse
import csv
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from services.registry import ensure_indexes, validate_record


def load_records(path):
    with path.open(encoding='utf-8-sig', newline='') as source:
        if path.suffix.lower() == '.csv':
            rows = list(csv.DictReader(source))
        elif path.suffix.lower() == '.json':
            rows = json.load(source)
        else:
            raise ValueError('Use a CSV or JSON file.')
    if not isinstance(rows, list) or not rows:
        raise ValueError('The dataset must be a non-empty list of records.')
    records = [validate_record(row) for row in rows]
    for key in ('student_id', 'university_email'):
        if len({record[key] for record in records}) != len(records):
            raise ValueError('The dataset contains duplicate student IDs or emails.')
    return records


def import_records(collection, records):
    """Insert new records without modifying existing identities or claim state."""
    ensure_indexes(collection)
    ids = [record['student_id'] for record in records]
    emails = [record['university_email'] for record in records]
    existing = collection.find({'$or': [{'student_id': {'$in': ids}},
                                        {'university_email': {'$in': emails}}]},
                               {'student_id': 1, 'university_email': 1, 'full_name': 1, 'course': 1})
    by_id = {record['student_id']: record for record in existing}
    by_email = {record['university_email']: record for record in by_id.values()}
    pending = []
    for record in records:
        prior = by_id.get(record['student_id'])
        email_owner = by_email.get(record['university_email'])
        if prior is None and email_owner is None:
            pending.append(record)
        elif (prior is None or email_owner is None or prior['_id'] != email_owner['_id'] or
              any(prior.get(field) != record[field] for field in
                  ('student_id', 'university_email', 'full_name', 'course'))):
            raise ValueError('An existing registry entry conflicts with this import.')
    if pending:
        # Unique indexes remain the final defence against concurrent imports.
        # MongoDB standalone cannot make this multi-document insert transactional.
        collection.insert_many(pending, ordered=True)
    return len(pending), len(records) - len(pending)


def main():
    parser = argparse.ArgumentParser(description='Import a student registry; defaults to dry-run.')
    parser.add_argument('file', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Insert new records into MongoDB.')
    mode.add_argument('--dry-run', action='store_true', help='Validate only; this is the default.')
    args = parser.parse_args()
    print('Registry files may contain personal data. Use synthetic or pseudonymised data for development.')
    try:
        records = load_records(args.file)
        if args.apply:
            # The web application's registry identity cannot insert or manage indexes.
            # Read a named environment variable; .env is an ignored local convenience.
            load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
            uri = os.environ.get('REGISTRY_SEED_URI')
            if not uri:
                raise RuntimeError('REGISTRY_SEED_URI is required for imports.')
            with MongoClient(uri, serverSelectionTimeoutMS=3000) as client:
                collection = client.registry_db.student_registry
                inserted, unchanged = import_records(collection, records)
            print(f'Inserted {inserted} registry records; {unchanged} existing records left unchanged.')
        else:
            print(f'Dry run: {len(records)} records are valid. No data was written.')
    except (ValueError, OSError, PyMongoError, RuntimeError):
        raise SystemExit('Registry import failed. Check format, identifier conflicts and database connection. '
                         'A database error during insertion may have partially imported records; a rerun skips exact matches.')


if __name__ == '__main__':
    main()
