"""Append security events without recording secrets or raw identifiers."""
from datetime import datetime, timezone
from flask import current_app, has_request_context, request
from pymongo.errors import PyMongoError
import db


def record(event, user_id=None, case_reference=None, target_id=None, old_role=None, new_role=None):
    try:
        entry = {
            'event_type': event, 'user_id': user_id,
            'ip': request.remote_addr if has_request_context() else None,
            'timestamp': datetime.now(timezone.utc),
        }
        # Opaque case references support investigation without storing case text.
        if case_reference is not None:
            entry['case_reference'] = case_reference
        if target_id is not None:
            entry['target_id'] = target_id
        if old_role is not None:
            entry['old_role'] = old_role
        if new_role is not None:
            entry['new_role'] = new_role
        db.get_audit_collection(write=True).insert_one(entry)
    except (PyMongoError, RuntimeError):
        current_app.logger.warning('Security event could not be recorded.')
