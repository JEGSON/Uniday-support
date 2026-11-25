"""Validate a CSV/JSON registry; use --apply to insert after reviewing a dry run."""

import argparse
import csv
import json
import os
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app import create_app
import db
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


def main():
    parser = argparse.ArgumentParser(description='Import a student registry; defaults to dry-run.')
    parser.add_argument('file', type=Path)
    parser.add_argument('--apply', action='store_true', help='Insert records into MongoDB.')
    args = parser.parse_args()
    print('Registry files may contain personal data. Use synthetic or pseudonymised data for development.')
    try:
        records = load_records(args.file)
        if args.apply:
            # The web application's registry identity cannot insert or manage indexes.
            uri = os.environ.get('REGISTRY_SEED_URI')
            if not uri:
                raise RuntimeError('REGISTRY_SEED_URI is required for imports.')
            with MongoClient(uri, serverSelectionTimeoutMS=3000) as client:
                collection = client.registry_db.student_registry
                ensure_indexes(collection)
                collection.insert_many(records, ordered=True)
            print(f'Inserted {len(records)} registry records.')
        else:
            print(f'Dry run: {len(records)} records are valid. No data was written.')
    except (ValueError, OSError, PyMongoError, RuntimeError):
        raise SystemExit('Registry import failed. Check the format, uniqueness and database connection.')


if __name__ == '__main__':
    main()
