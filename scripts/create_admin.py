"""Provision an account: python -m scripts.create_admin --role staff|admin."""

import argparse
import getpass

from pymongo.errors import DuplicateKeyError, PyMongoError

from app import create_app
from services.users import create_privileged_user


def main():
    parser = argparse.ArgumentParser(description='Provision a local staff or admin account.')
    parser.add_argument('--role', choices=('staff', 'admin'), required=True)
    parser.add_argument('--activate', action='store_true',
                        help='Activate only after the operator has independently verified the person.')
    args = parser.parse_args()
    if args.activate:
        print('Activation relies on the operator independently verifying the person; this script cannot verify identity.')
    print('Choose a unique password of 15–128 characters. It will not appear as you type.')
    data = {
        'full_name': input('Full name: '), 'staff_id': input('Staff ID: '),
        'email': input('Email: '), 'password': getpass.getpass('Password: '),
        'confirm_password': getpass.getpass('Confirm password: '),
    }
    app = create_app()
    try:
        with app.app_context():
            create_privileged_user(data, args.role, activate=args.activate)
    except DuplicateKeyError:
        raise SystemExit('Account could not be created: an identifier is already in use.')
    except ValueError as exc:
        raise SystemExit(str(exc))
    except (PyMongoError, RuntimeError):
        raise SystemExit('Account could not be created: database unavailable.')
    print('Account created ' + ('active.' if args.activate else 'inactive.'))


if __name__ == '__main__':
    main()
