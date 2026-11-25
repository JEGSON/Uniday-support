"""Password policy and Argon2id hashing for account services."""

from pathlib import Path
import unicodedata

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

# OWASP's minimum Argon2id profile: 19 MiB, two passes, one lane. Benchmark
# on the deployment machine before raising costs to limit resource exhaustion.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
_common_passwords = frozenset(
    unicodedata.normalize('NFC', line).casefold()
    for name in ('common_passwords.txt', 'ncsc_100k_passwords.txt')
    for line in Path(__file__).with_name(name).read_text(encoding='utf-8').splitlines()
    if line
)


def validate_password(password):
    """Return a safe error message, or None when the password is acceptable."""
    if not isinstance(password, str):
        return 'Enter a valid password.'
    # Bound the input before normalization and then count normalized code points.
    if len(password) > 512:
        return 'Use a password between 15 and 128 characters.'
    password = unicodedata.normalize('NFC', password)
    try:
        password.encode('utf-8')
    except UnicodeEncodeError:
        return 'Enter a valid password.'
    if not 15 <= len(password) <= 128 or not password.strip():
        return 'Use a password between 15 and 128 characters.'
    if password.casefold() in _common_passwords:
        return 'Choose a less common password.'
    return None


def hash_password(password):
    if validate_password(password):
        raise ValueError('Password does not meet the password policy.')
    return _hasher.hash(unicodedata.normalize('NFC', password))


def verify_password(password_hash, password):
    # Bound inputs before the expensive KDF and treat malformed hashes as failure.
    if not isinstance(password, str) or len(password) > 512 or not isinstance(password_hash, str):
        return False
    password = unicodedata.normalize('NFC', password)
    if not 1 <= len(password) <= 128:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError, UnicodeEncodeError):
        return False


def needs_rehash(password_hash):
    return _hasher.check_needs_rehash(password_hash)


def rehash_verified_password(password):
    """Rehash only after successful authentication, without imposing new policy."""
    return _hasher.hash(unicodedata.normalize('NFC', password))
