"""Create account indexes: python -m scripts.setup_indexes."""

from app import create_app
from db import ensure_user_indexes


def main():
    app = create_app()
    with app.app_context():
        ensure_user_indexes()
    print('Account indexes are ready.')


if __name__ == '__main__':
    main()
