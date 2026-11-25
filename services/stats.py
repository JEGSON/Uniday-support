"""Aggregate case metadata without returning descriptions or staff notes."""
import db


def get_admin_overview(user):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'role', None) != 'admin':
        raise PermissionError('Administrator access required.')
    # Grouping happens inside MongoDB: no individual case is returned to Flask.
    pipeline = [{'$group': {'_id': {'status': '$status', 'category': '$category'}, 'count': {'$sum': 1}}}]
    groups = list(db.get_stats_cases().aggregate(pipeline))
    labels = {'Wellbeing': 'Personal support', 'Disability': 'Personal support',
              'Academic': 'Study support', 'Financial': 'Practical support',
              'Accommodation': 'Practical support', 'Something else': 'Other support'}
    totals = {}
    opened = waiting = 0
    for group in groups:
        status, category, count = group['_id'].get('status'), group['_id'].get('category'), group['count']
        if status != 'Done':
            opened += count
        if status == 'Awaiting Student':
            waiting += count
        label = labels.get(category, 'Other support')
        totals[label] = totals.get(label, 0) + count
    # Suppress every category if any non-zero bucket is small; otherwise the
    # hidden value could be calculated by subtracting the other counts.
    suppress = any(0 < count < 5 for count in totals.values())
    return {'open_requests': opened, 'awaiting_reply': waiting,
            'categories': [{'label': label, 'count': None if suppress else count}
                           for label, count in sorted(totals.items())]}
