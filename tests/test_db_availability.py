from unittest.mock import patch

import pytest
from pymongo.errors import ServerSelectionTimeoutError

import db
from app import create_app


def test_pages_load_when_indexes_cannot_be_created():
    with patch.dict('os.environ', {'MONGODB_URI': 'mongodb://localhost:27017'}), patch(
        'db.ensure_user_indexes', side_effect=ServerSelectionTimeoutError('unavailable')
    ):
        app = create_app()
    assert app.test_client().get('/').status_code == 200
    assert app.test_client().get('/signup').status_code == 200


def test_account_collection_fails_closed_when_indexes_are_unavailable():
    with patch.dict('os.environ', {'MONGODB_URI': 'mongodb://localhost:27017'}), patch('db.ensure_user_indexes'):
        app = create_app()
    with app.app_context(), patch('db.ensure_user_indexes', side_effect=ServerSelectionTimeoutError('unavailable')):
        with pytest.raises(ServerSelectionTimeoutError):
            db.get_users()


def test_pages_load_without_database_configuration():
    with patch.dict('os.environ', {'MONGODB_URI': ''}), patch('db.dotenv_values', return_value={}):
        app = create_app()
    assert app.test_client().get('/').status_code == 200
    with app.app_context(), pytest.raises(RuntimeError, match='MONGODB_URI'):
        db.get_users()
