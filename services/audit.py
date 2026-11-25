"""Append security events without recording secrets or raw identifiers."""
from datetime import datetime, timezone
from flask import current_app, has_request_context, request
from pymongo.errors import PyMongoError
import db


def record(event, user_id=None, case_reference=None):
    try:
        entry = {
            'event_type': event, 'user_id': user_id,
            'ip': request.remote_addr if has_request_context() else None,
            'timestamp': datetime.now(timezone.utc),
        }
        # Opaque case references support investigation without storing case text.
        if case_reference is not None:
            entry['case_reference'] = case_reference
        db.get_db('MONGODB_AUDIT_DB').events.insert_one(entry)
    except (PyMongoError, RuntimeError):
        current_app.logger.warning('Security event could not be recorded.')
