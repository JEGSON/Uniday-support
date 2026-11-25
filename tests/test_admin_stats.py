from types import SimpleNamespace
from unittest.mock import patch

import pytest
from services import stats


def test_aggregation_returns_counts_only_and_suppresses_small_buckets():
    user = SimpleNamespace(is_authenticated=True, role='admin')
    class Collection:
        def aggregate(self, pipeline):
            assert pipeline == [{'$group': {'_id': {'status': '$status', 'category': '$category'}, 'count': {'$sum': 1}}}]
            return [{'_id': {'status': 'Received', 'category': 'Wellbeing'}, 'count': 2},
                    {'_id': {'status': 'Done', 'category': 'Academic'}, 'count': 7}]
    with patch('db.get_stats_cases', return_value=Collection()):
        result = stats.get_admin_overview(user)
    assert result['open_requests'] == 2
    assert all(item['count'] is None for item in result['categories'])
    assert set(result) == {'open_requests', 'awaiting_reply', 'categories'}


def test_stats_reject_non_admin():
    with pytest.raises(PermissionError):
        stats.get_admin_overview(SimpleNamespace(is_authenticated=True, role='staff'))


def test_audit_filters_ignore_hostile_input_and_limit_results():
    from services.audit_viewer import get_events
    user = SimpleNamespace(is_authenticated=True, role='admin')
    class Cursor:
        def sort(self, *args): return self
        def skip(self, n):
            assert n == 0
            return self
        def limit(self, n):
            assert n == 51
            return []
    class Collection:
        def find(self, query, projection):
            assert query == {}
            assert 'password_hash' not in projection
            return Cursor()
    with patch('db.get_audit_collection', return_value=Collection()):
        result, page, more = get_events(user, {'type': {'$ne': ''}, 'user': {'$ne': ''}, 'start': 'bad', 'page': '999999'})
    assert result == [] and page == 1 and not more
