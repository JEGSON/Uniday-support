from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.tokens import generate_token, new_token_record, token_hash, token_matches


def test_token_is_random_and_only_hash_is_stored():
    first, second = generate_token(), generate_token()
    record = new_token_record('user', first)
    assert first != second and first not in repr(record)
    assert record['token_hash'] == token_hash(first)
    assert token_matches(first, record)


def test_invalid_expired_and_used_tokens_fail():
    now = datetime.now(timezone.utc)
    token = generate_token()
    record = new_token_record('user', token, now)
    assert not token_matches('tampered', record, now)
    assert not token_matches(token, record, now + timedelta(minutes=30))
    assert not token_matches(token, dict(record, used_at=now), now)


def test_hash_comparison_uses_compare_digest():
    token = generate_token()
    record = new_token_record('user', token)
    with patch('services.tokens.hmac.compare_digest', return_value=True) as compare:
        assert token_matches(token, record)
    compare.assert_called_once_with(token_hash(token), record['token_hash'])
