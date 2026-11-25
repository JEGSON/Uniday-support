"""Append security events without recording secrets or raw identifiers."""
from datetime import datetime, timezone
from flask import current_app, has_request_context, request
from pymongo.errors import PyMongoError
import db


def record(event, user_id=None):
    try:
        db.get_db('MONGODB_AUDIT_DB').events.insert_one({
            'event_type': event, 'user_id': user_id,
            'ip': request.remote_addr if has_request_context() else None,
            'timestamp': datetime.now(timezone.utc),
        })
    except (PyMongoError, RuntimeError):
        current_app.logger.warning('Security event could not be recorded.')
