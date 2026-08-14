"""Discord actions performed over the REST API (no gateway needed).

Plain sync functions: the Django web views call them directly, and the
discord.py gateway worker calls them via ``asyncio.to_thread(...)``.

Layout: constants and routes first, then the public API, then HTTP internals.
"""

import logging
import time

import httpx
from django.conf import settings

from bot.channels import CHANNEL_TEMPLATE

logger = logging.getLogger(__name__)

API_BASE = "https://discord.com/api/v10"
VIEW_CHANNEL = 1 << 10  # 1024
CATEGORY = 4
CHANNEL_TYPE = {"text": 0, "voice": 2}
TEST_ROLE_NAMES = ("Admin", "Base", "Guest", "Product Owners")


class TestRoleError(Exception):
    """Test roles are missing or ambiguous."""


# --- Routes (all URL construction lives here) ---


def _guild() -> str:
    return str(settings.DISCORD_GUILD_ID)


def _roles_route() -> str:
    return f"/guilds/{_guild()}/roles"


def _role_route(role_id: str) -> str:
    return f"/guilds/{_guild()}/roles/{role_id}"


def _channels_route() -> str:
    return f"/guilds/{_guild()}/channels"


def _channel_route(channel_id: str) -> str:
    return f"/channels/{channel_id}"


def _member_route(user_id: str) -> str:
    return f"/guilds/{_guild()}/members/{user_id}"


def _member_role_route(user_id: str, role_id: str) -> str:
    return f"/guilds/{_guild()}/members/{user_id}/roles/{role_id}"


# --- Public API ---


def setup_test_roles(promotion_names: list[str]) -> dict[str, str]:
    """Find or create every role required by the test fixture."""
    names = _test_role_names(promotion_names)
    with _client() as client:
        roles = _get_roles(client)
        role_ids = {}

        for name in names:
            role = _find_test_role(roles, name)
            if role is None:
                role = _create_test_role(client, name)
                roles.append(role)
                logger.info("Created test role %s (%s)", name, role["id"])
            role_ids[name] = str(role["id"])

    settings.DISCORD_ADMIN_ROLE_ID = role_ids["Admin"]
    settings.DISCORD_BASE_ROLE_ID = role_ids["Base"]
    settings.DISCORD_GUEST_ROLE_ID = role_ids["Guest"]
    settings.DISCORD_PRODUCT_OWNERS_ROLE_ID = role_ids["Product Owners"]
    return role_ids


def resolve_test_roles(promotion_names: list[str] | None = None) -> dict[str, str]:
    """Resolve test roles without creating or modifying anything."""
    names = _test_role_names(promotion_names or [])
    with _client() as client:
        roles = _get_roles(client)
    role_ids = {}
    for name in names:
        role = _find_test_role(roles, name)
        if role is None:
            raise TestRoleError(f"Discord role is missing; restart runbot: {name}")
        role_ids[name] = str(role["id"])
    return role_ids


def create_class_category(
    name: str, campus: str, existing_role_id: str | None = None
) -> tuple[str, str]:
    """Idempotently create a class role + private category + channel template.

    Returns the role and category ids. Called by the learnd webhook.
    """
    if settings.CODAEMON_TEST_MODE:
        role_ids = resolve_test_roles()
        settings.DISCORD_PRODUCT_OWNERS_ROLE_ID = role_ids["Product Owners"]

    class_name = _class_name(name, campus)
    with _client() as client:
        role = None
        if existing_role_id:
            role = _find_role_by_id(client, existing_role_id)
        if role is None:
            role = _find_role(client, class_name)
        if role is None:
            role = _create_role(client, class_name)
            logger.info("Created role %s (%s)", class_name, role["id"])

        category = _find_category(client, class_name)
        if category is None:
            category = _create_category(client, class_name, role["id"])
            logger.info("Created category and channels for %s", class_name)
        else:
            logger.info("Category %s already exists, skipping creation", class_name)
        _ensure_channels(client, category["id"])

        return role["id"], category["id"]


def reconcile_class_category(
    name: str,
    campus: str,
    role_id: str,
    category_id: str,
) -> tuple[str, str]:
    """Create or complete the active Discord resources for one learnd class."""
    class_name = _class_name(name, campus)
    with _client() as client:
        role = _find_role_by_id(client, role_id) if role_id else None
        if role is None:
            role = _find_role(client, class_name)
        if role is None:
            role = _create_role(client, class_name)

        category = _find_category_by_id(client, category_id) if category_id else None
        if category is None:
            category = _find_category(client, class_name)
        if category is None:
            category = _create_category(client, class_name, role["id"])
        _ensure_channels(client, category["id"])
        return role["id"], category["id"]


def archive_class_resources(
    name: str,
    campus: str,
    start_year: int,
    role_id: str,
    category_id: str,
) -> None:
    """Give one retained class role and category their archived name."""
    class_name = _class_name(name, campus)
    archived_name = _archived_class_name(name, campus, start_year)
    with _client() as client:
        role = _find_role_by_id(client, role_id) if role_id else None
        if role is None:
            role = _find_role(client, class_name)
        if role is not None and role["name"] != archived_name:
            _request(client, "PATCH", _role_route(role["id"]), {"name": archived_name})

        category = _find_category_by_id(client, category_id) if category_id else None
        if category is None:
            category = _find_category(client, class_name)
        if category is not None and category["name"] != archived_name:
            _request(client, "PATCH", _channel_route(category["id"]), {"name": archived_name})


def delete_class_resources(
    name: str,
    campus: str,
    start_year: int,
    role_id: str,
    category_id: str,
) -> None:
    """Delete one old class category, all its channels, and its role."""
    archived_name = _archived_class_name(name, campus, start_year)
    with _client() as client:
        category = _find_category_by_id(client, category_id) if category_id else None
        if category is None and role_id:
            category = _find_category_by_role_id(client, role_id)
        if category is None:
            category = _find_category(client, archived_name)
        if category is not None:
            _delete_category(client, category["id"])

        role = _find_role_by_id(client, role_id) if role_id else None
        if role is None:
            role = _find_role(client, archived_name)
        if role is not None:
            _request(client, "DELETE", _role_route(role["id"]))


def create_category(name: str) -> str:
    """Idempotently create a private category + channel template (no role).

    Called by the ``/createcategory`` slash command.
    """
    with _client() as client:
        category = _find_category(client, name)
        if category is None:
            category = _create_category(client, name, role_id=None)
            logger.info("Created category %s", name)
        _ensure_channels(client, category["id"])
        return category["id"]


def delete_category(category_id: str) -> None:
    """Delete a category and every channel it contains."""
    with _client() as client:
        _delete_category(client, category_id)


def apply_onboarding(
    user_id: str,
    nickname: str,
    add_role_ids: list[str],
    remove_role_ids: list[str],
) -> None:
    """Set a member's nickname, add roles, and remove roles (onboarding)."""
    with _client() as client:
        _request(client, "PATCH", _member_route(user_id), {"nick": nickname})
        for role_id in add_role_ids:
            if role_id:
                _request(client, "PUT", _member_role_route(user_id, role_id))
        for role_id in remove_role_ids:
            if role_id:
                _request(client, "DELETE", _member_role_route(user_id, role_id))
        logger.info("Applied onboarding for member %s (%s)", user_id, nickname)


def reset_member(user_id: str, promotion_role_ids: list[str]) -> None:
    """Restore a member's nickname and onboarding roles."""
    remove_role_ids = list(dict.fromkeys([settings.DISCORD_BASE_ROLE_ID, *promotion_role_ids]))
    with _client() as client:
        _request(client, "PATCH", _member_route(user_id), {"nick": None})
        if settings.DISCORD_GUEST_ROLE_ID:
            _request(client, "PUT", _member_role_route(user_id, settings.DISCORD_GUEST_ROLE_ID))
        for role_id in remove_role_ids:
            if role_id:
                _request(client, "DELETE", _member_role_route(user_id, role_id))
        logger.info("Reset member %s", user_id)


# --- Internals ---


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": f"Bot {settings.DISCORD_TOKEN}"},
        timeout=30,
    )


def _test_role_names(promotion_names: list[str]) -> list[str]:
    promotion_roles = {}
    reserved = {name.casefold() for name in (*TEST_ROLE_NAMES, "@everyone")}
    for raw_name in promotion_names:
        name = raw_name.strip()
        if not name:
            raise TestRoleError("Promotion role names cannot be empty.")
        key = name.casefold()
        if key in reserved:
            raise TestRoleError(f"Promotion role name is reserved: {name}")
        existing = promotion_roles.get(key)
        if existing and existing != name:
            raise TestRoleError(f"Promotion role names differ only by case: {existing}, {name}")
        promotion_roles[key] = name
    return [*TEST_ROLE_NAMES, *promotion_roles.values()]


def _get_roles(client: httpx.Client) -> list[dict]:
    return _request(client, "GET", _roles_route()).json()


def _find_test_role(roles: list[dict], name: str) -> dict | None:
    matches = [role for role in roles if role["name"] == name]
    if len(matches) > 1:
        raise TestRoleError(f"Multiple Discord roles are named {name}.")
    if not matches:
        return None
    role = matches[0]
    if role.get("managed"):
        raise TestRoleError(f"Discord role is managed by an integration: {name}")
    return role


def _class_name(name: str, campus: str) -> str:
    return f"{name} - {campus}"


def _archived_class_name(name: str, campus: str, start_year: int) -> str:
    return (
        f"{_class_name(name, campus)} · arch. {start_year % 100:02d}-{(start_year + 1) % 100:02d}"
    )


def _category_overwrites(role_id: str | None) -> list[dict]:
    overwrites = [
        # Deny @everyone (its id == the guild id) so the class area is private.
        {"id": str(settings.DISCORD_EVERYONE_ROLE_ID), "type": 0, "deny": str(VIEW_CHANNEL)},
        {"id": str(settings.DISCORD_PRODUCT_OWNERS_ROLE_ID), "type": 0, "allow": str(VIEW_CHANNEL)},
    ]
    if role_id:
        overwrites.append({"id": str(role_id), "type": 0, "allow": str(VIEW_CHANNEL)})
    return overwrites


def _find_role(client: httpx.Client, name: str) -> dict | None:
    return next((role for role in _get_roles(client) if role["name"] == name), None)


def _find_role_by_id(client: httpx.Client, role_id: str) -> dict | None:
    return next((role for role in _get_roles(client) if role["id"] == str(role_id)), None)


def _find_category(client: httpx.Client, name: str) -> dict | None:
    channels = _request(client, "GET", _channels_route()).json()
    return next(
        (
            channel
            for channel in channels
            if channel["type"] == CATEGORY and channel["name"] == name
        ),
        None,
    )


def _find_category_by_id(client: httpx.Client, category_id: str) -> dict | None:
    channels = _request(client, "GET", _channels_route()).json()
    return next(
        (
            channel
            for channel in channels
            if channel["type"] == CATEGORY and channel["id"] == str(category_id)
        ),
        None,
    )


def _find_category_by_role_id(client: httpx.Client, role_id: str) -> dict | None:
    channels = _request(client, "GET", _channels_route()).json()
    return next(
        (
            channel
            for channel in channels
            if channel["type"] == CATEGORY
            and any(
                str(overwrite.get("id")) == str(role_id)
                for overwrite in channel.get("permission_overwrites", [])
            )
        ),
        None,
    )


def _create_role(client: httpx.Client, name: str) -> dict:
    return _request(
        client,
        "POST",
        _roles_route(),
        {"name": name, "hoist": True, "mentionable": True},
    ).json()


def _create_test_role(client: httpx.Client, name: str) -> dict:
    return _request(
        client,
        "POST",
        _roles_route(),
        {"name": name, "permissions": "0", "hoist": False, "mentionable": False},
    ).json()


def _create_category(client: httpx.Client, name: str, role_id: str | None) -> dict:
    return _request(
        client,
        "POST",
        _channels_route(),
        {
            "name": name,
            "type": CATEGORY,
            "permission_overwrites": _category_overwrites(role_id),
        },
    ).json()


def _ensure_channels(client: httpx.Client, parent_id: str) -> None:
    existing_channels = _request(client, "GET", _channels_route()).json()
    for channel in CHANNEL_TEMPLATE:
        channel_type = CHANNEL_TYPE[channel["type"]]
        exists = any(
            existing.get("parent_id") == str(parent_id)
            and existing["name"] == channel["name"]
            and existing["type"] == channel_type
            for existing in existing_channels
        )
        if exists:
            continue
        _request(
            client,
            "POST",
            _channels_route(),
            {
                "name": channel["name"],
                "type": channel_type,
                "parent_id": parent_id,
            },
        )


def _delete_category(client: httpx.Client, category_id: str) -> None:
    channels = _request(client, "GET", _channels_route()).json()
    children = [channel for channel in channels if channel.get("parent_id") == str(category_id)]
    for child in children:
        _request(client, "DELETE", _channel_route(child["id"]))
    _request(client, "DELETE", _channel_route(category_id))
    logger.info("Deleted category %s (%d channels)", category_id, len(children))


def _request(
    client: httpx.Client,
    method: str,
    route: str,
    payload: dict | None = None,
) -> httpx.Response:
    for _attempt in range(5):
        response = client.request(method, route, json=payload)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        retry_after = float(response.json().get("retry_after", 1))
        time.sleep(retry_after)
    response.raise_for_status()
    return response
