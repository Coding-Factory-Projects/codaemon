"""Discord member operations."""

import logging

from django.conf import settings

from bot.discord_api import client as discord

logger = logging.getLogger(__name__)


def apply_onboard(
    user_id: str,
    nickname: str,
    add_role_ids: list[str],
    remove_role_ids: list[str],
) -> None:
    """Set a member's nickname and onboarding roles."""
    with discord.create_client() as client:
        discord.request(client, "PATCH", discord.member_route(user_id), {"nick": nickname})
        for role_id in add_role_ids:
            if role_id:
                discord.request(client, "PUT", discord.member_role_route(user_id, role_id))
        for role_id in remove_role_ids:
            if role_id:
                discord.request(client, "DELETE", discord.member_role_route(user_id, role_id))
        logger.info("Applied onboarding for member %s (%s)", user_id, nickname)


def reset_member(user_id: str, promotion_role_ids: list[str]) -> None:
    """Restore a member's nickname and onboarding roles."""
    remove_role_ids = list(dict.fromkeys([settings.DISCORD_BASE_ROLE_ID, *promotion_role_ids]))
    with discord.create_client() as client:
        discord.request(client, "PATCH", discord.member_route(user_id), {"nick": None})
        if settings.DISCORD_GUEST_ROLE_ID:
            discord.request(
                client,
                "PUT",
                discord.member_role_route(user_id, settings.DISCORD_GUEST_ROLE_ID),
            )
        for role_id in remove_role_ids:
            if role_id:
                discord.request(client, "DELETE", discord.member_role_route(user_id, role_id))
        logger.info("Reset member %s", user_id)
