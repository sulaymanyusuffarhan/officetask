from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


password_hasher = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=2)
# Used for unknown usernames so a missing account does not skip the expensive Argon2 check.
DUMMY_PASSWORD_HASH = password_hasher.hash("not-a-real-office-task-password")


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Passwords must contain at least 12 characters")
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
