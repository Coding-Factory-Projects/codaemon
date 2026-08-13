"""HTTP client for learnd (formerly TeachPilot), the roster system of record."""

import json
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class LearndError(Exception):
    """The learnd service or fixture could not return a usable student."""


class StudentNotFound(LearndError):
    """No student matches the supplied email address."""


def patch_student(email: str, discord_id: str) -> dict:
    """Bind a Discord id to a student by email and read back their name + promotion role.

    Mirrors the existing contract:
        PATCH {LEARND_BASE_URL}/promotions/students  {email, discord_id}
        -> {"firstName", "lastName", "promotion": {"discord_role_id"}}
    """
    if settings.CODAEMON_TEST_MODE:
        return _fixture_student(email, discord_id)

    url = f"{settings.LEARND_BASE_URL.rstrip('/')}/promotions/students"
    try:
        resp = httpx.patch(
            url,
            json={"email": email, "discord_id": discord_id},
            headers={settings.SHARED_SECRET_HEADER: settings.SHARED_SECRET},
            timeout=30,
        )
        if resp.status_code == 404:
            raise StudentNotFound(email)
        resp.raise_for_status()
        student = resp.json()
    except StudentNotFound:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise LearndError("learnd request failed") from exc
    return _validate_student(student, "discord_role_id")


def fixture_promotion_names() -> list[str]:
    """Return every promotion role name declared by the test fixture."""
    return [
        _validate_student(student, "discord_role_name")["promotion"]["discord_role_name"]
        for student in _read_fixture().values()
    ]


def _fixture_student(email: str, discord_id: str) -> dict:
    """Load one student from the test fixture, re-reading it for every request."""
    fixture = _read_fixture()
    normalized_email = email.strip().casefold()
    student = next(
        (
            value
            for fixture_email, value in fixture.items()
            if fixture_email.strip().casefold() == normalized_email
        ),
        None,
    )
    if student is None:
        raise StudentNotFound(email)

    logger.info("Fixture matched %s to Discord member %s", email, discord_id)
    return _validate_student(student, "discord_role_name")


def _read_fixture() -> dict[str, object]:
    try:
        fixture = json.loads(settings.LEARND_FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LearndError(f"cannot read fixture {settings.LEARND_FIXTURE_PATH}") from exc

    if not isinstance(fixture, dict):
        raise LearndError("student fixture must be a JSON object")
    return fixture


def _validate_student(student: object, role_key: str) -> dict:
    if not isinstance(student, dict):
        raise LearndError("student response must be an object")
    promotion = student.get("promotion")
    if not isinstance(promotion, dict):
        raise LearndError("student response is missing promotion")

    first_name = student.get("firstName")
    last_name = student.get("lastName")
    role = promotion.get(role_key)

    if not isinstance(first_name, str):
        raise LearndError("student response contains invalid fields")
    if not first_name.strip():
        raise LearndError("student response contains invalid fields")
    if not isinstance(last_name, str):
        raise LearndError("student response contains invalid fields")
    if not last_name.strip():
        raise LearndError("student response contains invalid fields")
    if not isinstance(role, str):
        raise LearndError("student response contains invalid fields")
    if not role.strip():
        raise LearndError("student response contains invalid fields")

    return {
        "firstName": first_name.strip(),
        "lastName": last_name.strip(),
        "promotion": {role_key: role.strip()},
    }
