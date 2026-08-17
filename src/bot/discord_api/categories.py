"""Discord role, category, and channel operations."""

import logging

import httpx
from django.conf import settings

from bot.discord_api import client as discord
from bot.discord_api import testing_roles

logger = logging.getLogger(__name__)

VIEW_CHANNEL = 1 << 10
CATEGORY = 4
CHANNEL_TYPE = {"text": 0, "voice": 2}
CHANNEL_TEMPLATE = [
    {"name": "general", "type": "text"},
    {"name": "Classroom", "type": "voice"},
    {"name": "Presentation", "type": "voice"},
    {"name": "Groupe 1", "type": "voice"},
    {"name": "Groupe 2", "type": "voice"},
    {"name": "Groupe 3", "type": "voice"},
    {"name": "Groupe 4", "type": "voice"},
    {"name": "Groupe 5", "type": "voice"},
    {"name": "Groupe 6", "type": "voice"},
    {"name": "Groupe 7", "type": "voice"},
    {"name": "Groupe 8", "type": "voice"},
]


def create_class_category(
    name: str, campus: str, existing_role_id: str | None = None
) -> tuple[str, str]:
    """Idempotently create a class role, private category, and channel template."""
    if settings.CODAEMON_TEST_MODE:
        role_ids = testing_roles.resolve_testing_roles()
        settings.DISCORD_PRODUCT_OWNERS_ROLE_ID = role_ids["Product Owners"]

    class_name = _class_name(name, campus)
    with discord.create_client() as client:
        role = _find_role_by_id(client, existing_role_id) if existing_role_id else None
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
    with discord.create_client() as client:
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
    with discord.create_client() as client:
        role = _find_role_by_id(client, role_id) if role_id else None
        if role is None:
            role = _find_role(client, class_name)
        if role is not None and role["name"] != archived_name:
            discord.request(
                client, "PATCH", discord.role_route(role["id"]), {"name": archived_name}
            )

        category = _find_category_by_id(client, category_id) if category_id else None
        if category is None:
            category = _find_category(client, class_name)
        if category is not None and category["name"] != archived_name:
            discord.request(
                client,
                "PATCH",
                discord.channel_route(category["id"]),
                {"name": archived_name},
            )


def delete_class_resources(
    name: str,
    campus: str,
    start_year: int,
    role_id: str,
    category_id: str,
) -> None:
    """Delete one old class category, all its channels, and its role."""
    archived_name = _archived_class_name(name, campus, start_year)
    with discord.create_client() as client:
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
            discord.request(client, "DELETE", discord.role_route(role["id"]))


def create_category(name: str) -> str:
    """Idempotently create a private category and channel template without a role."""
    with discord.create_client() as client:
        category = _find_category(client, name)
        if category is None:
            category = _create_category(client, name, role_id=None)
            logger.info("Created category %s", name)
        _ensure_channels(client, category["id"])
        return category["id"]


def rename_category(category_id: str, role_id: str, name: str) -> None:
    """Give a category and its associated role the same new name."""
    with discord.create_client() as client:
        discord.request(client, "PATCH", discord.role_route(role_id), {"name": name})
        discord.request(client, "PATCH", discord.channel_route(category_id), {"name": name})


def delete_category(category_id: str) -> None:
    """Delete a category and every channel it contains."""
    with discord.create_client() as client:
        _delete_category(client, category_id)


def _class_name(name: str, campus: str) -> str:
    return f"{name} - {campus}"


def _archived_class_name(name: str, campus: str, start_year: int) -> str:
    return (
        f"{_class_name(name, campus)} · arch. {start_year % 100:02d}-{(start_year + 1) % 100:02d}"
    )


def _category_overwrites(role_id: str | None) -> list[dict]:
    overwrites = [
        {"id": str(settings.DISCORD_EVERYONE_ROLE_ID), "type": 0, "deny": str(VIEW_CHANNEL)},
        {
            "id": str(settings.DISCORD_PRODUCT_OWNERS_ROLE_ID),
            "type": 0,
            "allow": str(VIEW_CHANNEL),
        },
    ]
    if role_id:
        overwrites.append({"id": str(role_id), "type": 0, "allow": str(VIEW_CHANNEL)})
    return overwrites


def _get_roles(client: httpx.Client) -> list[dict]:
    return discord.request(client, "GET", discord.roles_route()).json()


def _find_role(client: httpx.Client, name: str) -> dict | None:
    return next((role for role in _get_roles(client) if role["name"] == name), None)


def _find_role_by_id(client: httpx.Client, role_id: str) -> dict | None:
    return next((role for role in _get_roles(client) if role["id"] == str(role_id)), None)


def _find_category(client: httpx.Client, name: str) -> dict | None:
    channels = discord.request(client, "GET", discord.channels_route()).json()
    return next(
        (
            channel
            for channel in channels
            if channel["type"] == CATEGORY and channel["name"] == name
        ),
        None,
    )


def _find_category_by_id(client: httpx.Client, category_id: str) -> dict | None:
    channels = discord.request(client, "GET", discord.channels_route()).json()
    return next(
        (
            channel
            for channel in channels
            if channel["type"] == CATEGORY and channel["id"] == str(category_id)
        ),
        None,
    )


def _find_category_by_role_id(client: httpx.Client, role_id: str) -> dict | None:
    channels = discord.request(client, "GET", discord.channels_route()).json()
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
    return discord.request(
        client,
        "POST",
        discord.roles_route(),
        {"name": name, "hoist": True, "mentionable": True},
    ).json()


def _create_category(client: httpx.Client, name: str, role_id: str | None) -> dict:
    return discord.request(
        client,
        "POST",
        discord.channels_route(),
        {
            "name": name,
            "type": CATEGORY,
            "permission_overwrites": _category_overwrites(role_id),
        },
    ).json()


def _ensure_channels(client: httpx.Client, parent_id: str) -> None:
    existing_channels = discord.request(client, "GET", discord.channels_route()).json()
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
        discord.request(
            client,
            "POST",
            discord.channels_route(),
            {
                "name": channel["name"],
                "type": channel_type,
                "parent_id": parent_id,
            },
        )


def _delete_category(client: httpx.Client, category_id: str) -> None:
    channels = discord.request(client, "GET", discord.channels_route()).json()
    children = [channel for channel in channels if channel.get("parent_id") == str(category_id)]
    for child in children:
        discord.request(client, "DELETE", discord.channel_route(child["id"]))
    discord.request(client, "DELETE", discord.channel_route(category_id))
    logger.info("Deleted category %s (%d channels)", category_id, len(children))
