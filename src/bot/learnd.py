"""HTTP client for learnd, the roster system of record."""

import json
import time
from collections import defaultdict
from typing import Literal, TypedDict

import httpx
from django.conf import settings

from config.constants import StudentBackend


class LearndError(Exception):
    """The learnd service or fixture returned unusable data."""


class StudentNotFound(LearndError):
    """No active student matches the supplied email address."""


class OnboardStudent(TypedDict):
    first_name: str
    last_name: str
    discord_role_id: str


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


class _SchoolStudent(TypedDict):
    id: str
    first_name: str
    last_name: str


class _AcademicYear(TypedDict):
    id: str
    start_year: int
    status: str


class _SchoolClass(TypedDict):
    id: str
    name: str
    campus: str
    academic_year_id: str
    academic_year_status: str
    discord_role_id: str
    discord_category_id: str


class LearndStatus(TypedDict):
    health_ok: bool
    health_latency_ms: int | None
    api_status: Literal["ok", "missing_token", "unauthorized", "unreachable", "invalid"]
    api_latency_ms: int | None
    active_years: list[int] | None
    school_class_count: int | None


def check_status() -> LearndStatus:
    """Check learnd health and authenticated API access without exposing data."""
    result: LearndStatus = {
        "health_ok": False,
        "health_latency_ms": None,
        "api_status": "unreachable",
        "api_latency_ms": None,
        "active_years": None,
        "school_class_count": None,
    }
    base_url = settings.LEARND_BASE_URL.rstrip("/")
    if not base_url:
        return result

    started_at = time.monotonic()
    try:
        response = httpx.get(f"{base_url}/health", timeout=10)
        response.raise_for_status()
        result["health_ok"] = True
    except httpx.HTTPError:
        pass
    result["health_latency_ms"] = round((time.monotonic() - started_at) * 1000)

    if not settings.LEARND_API_TOKEN:
        result["api_status"] = "missing_token"
        return result

    started_at = time.monotonic()
    try:
        with httpx.Client(
            base_url=f"{base_url}/api/v1/",
            headers={"Authorization": f"Bearer {settings.LEARND_API_TOKEN}"},
            timeout=10,
        ) as client:
            academic_years_response = client.get("academic-years/")
            academic_years_response.raise_for_status()
            school_classes_response = client.get("school-classes/")
            school_classes_response.raise_for_status()
        academic_years = academic_years_response.json()
        school_classes = school_classes_response.json()
        if not isinstance(academic_years, list):
            result["api_status"] = "invalid"
            return result
        if not isinstance(school_classes, list):
            result["api_status"] = "invalid"
            return result
        result["active_years"] = []
        for year in academic_years:
            if not isinstance(year, dict):
                continue
            if year.get("status") != "active":
                continue
            start_year = year.get("start_year")
            if not isinstance(start_year, int):
                continue
            result["active_years"].append(start_year)
        result["school_class_count"] = len(school_classes)
        result["api_status"] = "ok"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            result["api_status"] = "unauthorized"
    except httpx.HTTPError:
        pass
    except ValueError:
        result["api_status"] = "invalid"
    finally:
        result["api_latency_ms"] = round((time.monotonic() - started_at) * 1000)
    return result


def onboard_student(email: str, discord_user_id: str) -> OnboardStudent:
    """Bind a Discord user ID to the active student matching an email address."""
    if settings.STUDENT_BACKEND == StudentBackend.FIXTURE:
        return _fixture_student(email)

    students = _get_collection(
        "/school-students/",
        params={"email": email, "academic_year_status": "active"},
    )
    if not students:
        raise StudentNotFound(email)
    if len(students) != 1:
        raise LearndError("learnd returned multiple active students for the email")
    student = _validate_school_student(students[0])

    memberships = _get_collection(
        "/school-class-students/",
        params={"student": student["id"], "academic_year_status": "active"},
    )
    if len(memberships) != 1:
        raise LearndError("learnd student must belong to exactly one active school class")
    membership = memberships[0]
    if not isinstance(membership, dict):
        raise LearndError("learnd returned an invalid school class membership")
    school_class_id = _required_string(membership, "school_class")

    school_classes = _get_collection("/school-classes/", params={"id": school_class_id})
    if len(school_classes) != 1:
        raise LearndError("learnd did not return the student's active school class")
    school_class = _validate_school_class(school_classes[0])
    if not school_class["discord_role_id"]:
        raise LearndError("learnd school class has no Discord role ID")

    _request(
        "PATCH",
        f"/school-students/{student['id']}/",
        json={"discord_user_id": discord_user_id},
    )
    return {
        "first_name": student["first_name"],
        "last_name": student["last_name"],
        "discord_role_id": school_class["discord_role_id"],
    }


def fetch_rollover() -> RolloverData:
    """Fetch active and archived academic years and their school classes."""
    academic_years = [
        _validate_academic_year(value) for value in _get_collection("/academic-years/")
    ]
    active_years = [year for year in academic_years if year["status"] == "active"]
    if len(active_years) != 1:
        raise LearndError("learnd must return exactly one active academic year")

    classes_by_year: defaultdict[str, list[RolloverClass]] = defaultdict(list)
    for value in _get_collection("/school-classes/"):
        school_class = _validate_school_class(value)
        if school_class["academic_year_status"] not in {"active", "archived"}:
            continue
        classes_by_year[school_class["academic_year_id"]].append(
            {
                "id": school_class["id"],
                "name": school_class["name"],
                "campus": school_class["campus"],
                "discord_role_id": school_class["discord_role_id"],
                "discord_category_id": school_class["discord_category_id"],
            }
        )

    active_year = active_years[0]
    archived_years = [year for year in academic_years if year["status"] == "archived"]
    return {
        "active_year": {
            "start_year": active_year["start_year"],
            "school_classes": classes_by_year[active_year["id"]],
        },
        "archived_years": [
            {
                "start_year": year["start_year"],
                "school_classes": classes_by_year[year["id"]],
            }
            for year in archived_years
        ],
    }


def patch_school_class_discord_ids(
    school_class_id: str,
    role_id: str,
    category_id: str,
) -> None:
    """Persist Discord resource IDs after rollover provisioning."""
    _request(
        "PATCH",
        f"/school-classes/{school_class_id}/",
        json={"discord_role_id": role_id, "discord_category_id": category_id},
    )


def fixture_promotion_names() -> list[str]:
    """Return every promotion role name declared by the test fixture."""
    return [
        _validate_fixture_student(student)["discord_role_id"]
        for student in _read_fixture().values()
    ]


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    json: dict[str, str] | None = None,
) -> object:
    url = f"{settings.LEARND_BASE_URL.rstrip('/')}/api/v1{path}"
    try:
        response = httpx.request(
            method,
            url,
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {settings.LEARND_API_TOKEN}"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LearndError("learnd request failed") from exc


def _get_collection(path: str, *, params: dict[str, str] | None = None) -> list[object]:
    payload = _request("GET", path, params=params)
    if not isinstance(payload, list):
        raise LearndError("learnd collection response must be a list")
    return payload


def _fixture_student(email: str) -> OnboardStudent:
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
    return _validate_fixture_student(student)


def _read_fixture() -> dict[str, object]:
    try:
        fixture = json.loads(settings.LEARND_FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LearndError(f"cannot read fixture {settings.LEARND_FIXTURE_PATH}") from exc
    if not isinstance(fixture, dict):
        raise LearndError("student fixture must be a JSON object")
    return fixture


def _validate_fixture_student(value: object) -> OnboardStudent:
    if not isinstance(value, dict):
        raise LearndError("student fixture entry must be an object")
    promotion = value.get("promotion")
    if not isinstance(promotion, dict):
        raise LearndError("student fixture entry is missing promotion")
    return {
        "first_name": _required_string(value, "firstName"),
        "last_name": _required_string(value, "lastName"),
        "discord_role_id": _required_string(promotion, "discord_role_name"),
    }


def _validate_school_student(value: object) -> _SchoolStudent:
    if not isinstance(value, dict):
        raise LearndError("learnd returned an invalid school student")
    return {
        "id": _required_string(value, "id"),
        "first_name": _required_string(value, "first_name"),
        "last_name": _required_string(value, "last_name"),
    }


def _validate_academic_year(value: object) -> _AcademicYear:
    if not isinstance(value, dict):
        raise LearndError("learnd returned an invalid academic year")
    start_year = value.get("start_year")
    if not isinstance(start_year, int):
        raise LearndError("learnd academic year has an invalid start year")
    status = _required_string(value, "status")
    if status not in {"planned", "active", "archived"}:
        raise LearndError("learnd academic year has an invalid status")
    return {
        "id": _required_string(value, "id"),
        "start_year": start_year,
        "status": status,
    }


def _validate_school_class(value: object) -> _SchoolClass:
    if not isinstance(value, dict):
        raise LearndError("learnd returned an invalid school class")
    status = _required_string(value, "academic_year_status")
    if status not in {"planned", "active", "archived"}:
        raise LearndError("learnd school class has an invalid academic year status")
    return {
        "id": _required_string(value, "id"),
        "name": _required_string(value, "name"),
        "campus": _required_string(value, "campus_name"),
        "academic_year_id": _required_string(value, "academic_year"),
        "academic_year_status": status,
        "discord_role_id": _string(value, "discord_role_id"),
        "discord_category_id": _string(value, "discord_category_id"),
    }


def _required_string(value: dict, key: str) -> str:
    result = _string(value, key)
    if not result:
        raise LearndError(f"learnd response field {key} must not be empty")
    return result


def _string(value: dict, key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str):
        raise LearndError(f"learnd response field {key} must be a string")
    return result.strip()
