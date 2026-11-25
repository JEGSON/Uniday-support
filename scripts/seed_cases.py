"""Add fictional demo cases; default is a dry run, never delete existing records."""
import argparse
from bson import ObjectId
from app import create_app
from services.auth import User
from services.cases import create_student_case


def main():
    parser = argparse.ArgumentParser(description='Create synthetic local case examples.')
    parser.add_argument('--apply', action='store_true', help='Insert five fictional examples.')
    args = parser.parse_args()
    if not args.apply:
        print('Dry run: five fictional examples would be inserted; nothing changed.')
        return
    app = create_app()
    with app.app_context():
        # A synthetic owner prevents these examples appearing in a real student account.
        user = User({'_id': ObjectId(), 'role': 'student'})
        for category in ('Academic', 'Wellbeing', 'Financial', 'Disability', 'Accommodation'):
            create_student_case(user, category, 'Fictional example for local testing.', False)
    print('Inserted five fictional cases; each run adds another five.')


if __name__ == '__main__':
    main()
