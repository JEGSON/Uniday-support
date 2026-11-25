import pytest
from argon2 import PasswordHasher

from services.passwords import hash_password, needs_rehash, validate_password, verify_password


def test_password_hash_round_trip_and_salt():
    password = 'a long passphrase with spaces'
    first = hash_password(password)
    second = hash_password(password)
    assert first.startswith('$argon2id$') and first != second
    assert verify_password(first, password)
    assert not verify_password(first, 'incorrect password')
    assert not needs_rehash(first)


def test_rehash_detects_old_parameters():
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash('a long passphrase with spaces')
    assert needs_rehash(old_hash)


@pytest.mark.parametrize('password', [None, {'$ne': ''}, '', 'short', ' ' * 15, 'x' * 129, 'PASSWORDPASSWORD'])
def test_password_policy_rejects_invalid_values(password):
    assert validate_password(password)
    with pytest.raises(ValueError):
        hash_password(password)


def test_password_policy_allows_spaces_and_long_passphrases():
    assert validate_password('my long passphrase is here') is None
    assert validate_password('a' * 128) is None


def test_verification_rejects_invalid_inputs():
    assert not verify_password('not a hash', 'a valid length password')
    assert not verify_password(None, 'a valid length password')
    assert not verify_password('not a hash', {'$ne': ''})


def test_bundled_breach_list_and_service_specific_passwords():
    assert validate_password('123456789987654321') == 'Choose a less common password.'
    assert validate_password('UNIDAYSSUPPORT123') == 'Choose a less common password.'
    assert validate_password('prefix 123456789987654321 suffix') is None


def test_unicode_normalization_is_consistent():
    composed = 'a long café passphrase'
    decomposed = 'a long cafe\u0301 passphrase'
    password_hash = hash_password(composed)
    assert verify_password(password_hash, decomposed)
    assert validate_password('a' * 15 + '\ud800') == 'Enter a valid password.'
