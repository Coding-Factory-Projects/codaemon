"""Signed, expiring onboarding tokens.

The emailed link carries a signed token instead of raw discord_id/email, so the
public /change-status endpoint can trust the values without a shared secret.
"""

from django.core import signing

SALT = "codaemon.onboarding"
DEFAULT_MAX_AGE = 3600  # 1 hour


def make_token(discord_id: str, email: str) -> str:
    return signing.dumps({"discord_id": str(discord_id), "email": email}, salt=SALT)


def read_token(token: str, max_age: int = DEFAULT_MAX_AGE) -> dict:
    """Return the payload dict, or raise django.core.signing.BadSignature
    (SignatureExpired is a subclass) if invalid or expired."""
    return signing.loads(token, salt=SALT, max_age=max_age)
