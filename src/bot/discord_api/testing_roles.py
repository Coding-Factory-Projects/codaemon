"""Discord role setup for the fixture student backend."""

import logging

import httpx
from django.conf import settings

from bot.discord_api import client as discord

logger = logging.getLogger(__name__)

TEST_ROLE_NAMES = ("Admin", "Base", "Guest", "Product Owners")


class TestRoleError(Exception):
    """Fixture roles are missing or ambiguous."""


def setup_testing_roles(promotion_names: list[str]) -> dict[str, str]:
    """Find or create every role required by the test fixture."""
    names = _test_role_names(promotion_names)
    with discord.create_client() as client:
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


def resolve_testing_roles(promotion_names: list[str] | None = None) -> dict[str, str]:
    """Resolve fixture roles without creating or modifying anything."""
    names = _test_role_names(promotion_names or [])
    with discord.create_client() as client:
        roles = _get_roles(client)
    role_ids = {}
    for name in names:
        role = _find_test_role(roles, name)
        if role is None:
            raise TestRoleError(f"Discord role is missing; restart runbot: {name}")
        role_ids[name] = str(role["id"])
    return role_ids


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
    return discord.request(client, "GET", discord.roles_route()).json()


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


def _create_test_role(client: httpx.Client, name: str) -> dict:
    return discord.request(
        client,
        "POST",
        discord.roles_route(),
        {"name": name, "permissions": "0", "hoist": False, "mentionable": False},
    ).json()
