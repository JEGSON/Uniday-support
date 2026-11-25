"""Read a bounded audit timeline through a separate, read-only identity."""
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import db

EVENTS = {'login_success': 'signed in', 'login_failure': 'sign-in was unsuccessful',
          'logout': 'signed out', 'role_denial': 'was denied access',
          'account_lockout': 'account was temporarily locked', 'registry_claim': 'claimed a registry record',
          'registry_match_failure': 'registry match was unsuccessful', 'verification_email_sent': 'verification message was sent',
          'verification_success': 'verified an account', 'verification_failure': 'verification was unsuccessful',
          'token_expired': 'verification link expired', 'resend_requested': 'requested another verification link',
          'resend_rate_limited': 'verification resend was limited', 'case_claimed': 'claimed a case',
          'case_message': 'sent a case update', 'case_note': 'added a private note',
          'case_status': 'changed case status', 'case_archive': 'archived a case',
          'user_activated': 'activated an account', 'user_deactivated': 'deactivated an account',
          'role_changed': 'changed an account role', 'admin_action_denied': 'an admin action was denied'}


def _date(value):
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        result = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        return result if result.year < 9999 and result.strftime('%Y-%m-%d') == value else None
    except ValueError:
        return None


def get_events(user, filters):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'role', None) != 'admin':
        raise PermissionError('Administrator access required.')
    query = {}
    event_type = filters.get('type')
    if isinstance(event_type, str) and event_type in EVENTS:
        query['event_type'] = event_type
    raw_user = filters.get('user')
    if isinstance(raw_user, str) and ObjectId.is_valid(raw_user):
        query['user_id'] = {'$in': [ObjectId(raw_user), raw_user]}
    start, end = _date(filters.get('start')), _date(filters.get('end'))
    if start and end and start > end:
        start = end = None
    if start or end:
        query['timestamp'] = {}
        if start:
            query['timestamp']['$gte'] = start
        if end:
            query['timestamp']['$lt'] = end + timedelta(days=1)
    raw_page = filters.get('page', '1')
    page = min(max(int(raw_page), 1), 100) if isinstance(raw_page, str) and raw_page.isascii() and raw_page.isdigit() and len(raw_page) <= 3 else 1
    # Never return arbitrary event fields or secret-bearing legacy documents.
    projection = {'event_type': 1, 'user_id': 1, 'timestamp': 1, 'ip': 1, '_id': 0}
    rows = list(db.get_audit_collection().find(query, projection).sort([('timestamp', -1), ('_id', -1)]).skip((page-1)*50).limit(51))
    result = []
    for row in rows[:50]:
        event = row.get('event_type', '')
        timestamp = row.get('timestamp')
        result.append({'actor': str(row.get('user_id') or 'An account'), 'action': EVENTS.get(event, 'performed a recorded action'),
                       'type': event if event in EVENTS else 'other',
                       'when': timestamp.strftime('%d %b %Y, %H:%M UTC') if isinstance(timestamp, datetime) else 'Time unavailable',
                       'source': str(row.get('ip') or 'Unavailable')})
    return result, page, len(rows) > 50 and page < 100
