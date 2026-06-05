"""HTTP client for learnd (formerly TeachPilot), the roster system of record."""

import httpx
from django.conf import settings


def patch_student(email: str, discord_id: str) -> dict:
    """Bind a Discord id to a student by email and read back their name + promotion role.

    Mirrors the existing contract:
        PATCH {LEARND_BASE_URL}/promotions/students  {email, discord_id}
        -> {"firstName", "lastName", "promotion": {"discord_role_id"}}
    """
    url = f"{settings.LEARND_BASE_URL.rstrip('/')}/promotions/students"
    resp = httpx.patch(
        url,
        json={"email": email, "discord_id": discord_id},
        headers={settings.SHARED_SECRET_HEADER: settings.SHARED_SECRET},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
