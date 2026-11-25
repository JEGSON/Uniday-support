"""Configure and access the application's MongoDB connection."""

import os
from pathlib import Path

from dotenv import dotenv_values
from flask import current_app
from pymongo import MongoClient
from pymongo.errors import PyMongoError


def init_app(app):
    local_settings = dotenv_values(Path(app.root_path) / '.env', interpolate=False)
    app.config.update(
        MONGODB_URI=os.environ.get('MONGODB_URI', local_settings.get('MONGODB_URI')),
        MONGODB_AUTH_DB=os.environ.get('MONGODB_AUTH_DB', local_settings.get('MONGODB_AUTH_DB')) or 'auth_db',
        MONGODB_AUDIT_DB=os.environ.get('MONGODB_AUDIT_DB', local_settings.get('MONGODB_AUDIT_DB')) or 'audit_db',
        REGISTRY_URI=os.environ.get('REGISTRY_URI', local_settings.get('REGISTRY_URI')),
    )

    uri = app.config['MONGODB_URI']
    if app.config['REGISTRY_URI']:
        try:
            app.extensions['registry_mongodb'] = MongoClient(app.config['REGISTRY_URI'], connect=False,
                                                              serverSelectionTimeoutMS=3000, tz_aware=True)
        except (PyMongoError, ValueError):
            app.logger.warning('Registry database configuration is invalid.')
    if uri:
        try:
            # A shared client maintains a connection pool across requests.
            app.extensions['mongodb'] = MongoClient(uri, connect=False, serverSelectionTimeoutMS=3000, tz_aware=True)
            with app.app_context():
                ensure_user_indexes()
        except (PyMongoError, ValueError):
            # Don't include exception details: a connection URI may contain secrets.
            app.logger.warning('MongoDB account indexes unavailable; account operations are disabled until they can be verified.')


def get_db(config_key):
    """Get a database by its Flask configuration key."""
    client = current_app.extensions.get('mongodb')
    if client is None:
        raise RuntimeError('Set MONGODB_URI before accessing MongoDB.')
    return client.get_database(current_app.config[config_key])


def ensure_user_indexes():
    """Enforce uniqueness in MongoDB, including under concurrent sign-ups."""
    users = get_db('MONGODB_AUTH_DB').users
    users.create_index('email', unique=True, name='unique_email')
    # Staff and administrators may not have a student ID. Index only strings;
    # validation must still require a non-empty ID for students.
    users.create_index('student_id', unique=True, name='unique_student_id',
                       partialFilterExpression={'student_id': {'$type': 'string'}})
    users.create_index('staff_id', unique=True, name='unique_staff_id',
                       partialFilterExpression={'staff_id': {'$type': 'string'}})


def get_users():
    """Return the users collection only after enforcing its required indexes."""
    ensure_user_indexes()
    return get_db('MONGODB_AUTH_DB').users


def get_registry():
    client = current_app.extensions.get('registry_mongodb')
    if client is None:
        raise RuntimeError('REGISTRY_URI is required for student registration.')
    return client.registry_db.student_registry
