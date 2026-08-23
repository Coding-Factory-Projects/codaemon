"""HTTP client for learnd (formerly TeachPilot), the roster system of record."""

import json
import logging
from typing import TypedDict

import httpx
from django.conf import settings

from config.constants import StudentBackend

logger = logging.getLogger(__name__)


class LearndError(Exception):
    """The learnd service or fixture could not return a usable student."""


class StudentNotFound(LearndError):
    """No student matches the supplied email address."""


class RolloverClass(TypedDict):
    id: str
    name: str
    campus: str
    discord_role_id: str
    discord_category_id: str


class RolloverYear(TypedDict):
    start_year: int
    school_classes: list[RolloverClass]


class RolloverData(TypedDict):
    active_year: RolloverYear
    archived_years: list[RolloverYear]


def patch_student(email: str, discord_id: str) -> dict:
    """Bind a Discord id to a student by email and read back their name + promotion role.

    Mirrors the existing contract:
        PATCH {LEARND_BASE_URL}/promotions/students  {email, discord_id}
        -> {"firstName", "lastName", "promotion": {"discord_role_id"}}
    """
    if settings.STUDENT_BACKEND == StudentBackend.FIXTURE:
        return _fixture_student(email, discord_id)

    url = f"{settings.LEARND_BASE_URL.rstrip('/')}/promotions/students"
    try:
        resp = httpx.patch(
            url,
            json={"email": email, "discord_id": discord_id},
            headers={settings.SHARED_SECRET_HEADER: settings.LEARND_SHARED_SECRET},
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


def fetch_rollover() -> RolloverData:
    """Fetch the active and archived school years used by the rollover command."""
    url = f"{settings.LEARND_BASE_URL.rstrip('/')}/discord/rollover"
    try:
        response = httpx.get(
            url,
            headers={settings.SHARED_SECRET_HEADER: settings.LEARND_SHARED_SECRET},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LearndError("learnd rollover request failed") from exc
    if not isinstance(payload, dict):
        raise LearndError("learnd rollover response must be an object")
    active_year = _validate_rollover_year(payload.get("active_year"))
    archived = payload.get("archived_years")
    if not isinstance(archived, list):
        raise LearndError("learnd rollover response is missing archived_years")
    return {
        "active_year": active_year,
        "archived_years": [_validate_rollover_year(year) for year in archived],
    }


def patch_school_class_discord_ids(school_class_id: str, role_id: str, category_id: str) -> None:
    """Persist Discord resource ids after rollover provisioning."""
    url = f"{settings.LEARND_BASE_URL.rstrip('/')}/discord/school-classes/{school_class_id}"
    try:
        response = httpx.patch(
            url,
            json={"discord_role_id": role_id, "discord_category_id": category_id},
            headers={settings.SHARED_SECRET_HEADER: settings.LEARND_SHARED_SECRET},
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LearndError("learnd class update failed") from exc


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


def _validate_rollover_year(value: object) -> RolloverYear:
    if not isinstance(value, dict):
        raise LearndError("learnd rollover response contains an invalid year")
    start_year = value.get("start_year")
    school_classes = value.get("school_classes")
    if not isinstance(start_year, int):
        raise LearndError("learnd rollover year is missing start_year")
    if not isinstance(school_classes, list):
        raise LearndError("learnd rollover year is missing school_classes")
    return {
        "start_year": start_year,
        "school_classes": [_validate_rollover_class(item) for item in school_classes],
    }


def _validate_rollover_class(value: object) -> RolloverClass:
    if not isinstance(value, dict):
        raise LearndError("learnd rollover response contains an invalid class")
    school_class_id = value.get("id")
    name = value.get("name")
    campus = value.get("campus")
    role_id = value.get("discord_role_id")
    category_id = value.get("discord_category_id")
    if not isinstance(school_class_id, str):
        raise LearndError("learnd rollover class is missing id")
    if not isinstance(name, str):
        raise LearndError("learnd rollover class is missing name")
    if not isinstance(campus, str):
        raise LearndError("learnd rollover class is missing campus")
    if not isinstance(role_id, str):
        raise LearndError("learnd rollover class is missing discord_role_id")
    if not isinstance(category_id, str):
        raise LearndError("learnd rollover class is missing discord_category_id")
    if not school_class_id.strip():
        raise LearndError("learnd rollover class contains empty required fields")
    if not name.strip():
        raise LearndError("learnd rollover class contains empty required fields")
    if not campus.strip():
        raise LearndError("learnd rollover class contains empty required fields")
    return {
        "id": school_class_id.strip(),
        "name": name.strip(),
        "campus": campus.strip(),
        "discord_role_id": role_id.strip(),
        "discord_category_id": category_id.strip(),
    }


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
