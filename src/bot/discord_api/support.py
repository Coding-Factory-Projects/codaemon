"""Discord support notifications."""

import logging

from django.conf import settings

from bot.discord_api import client as discord

logger = logging.getLogger(__name__)


def report_onboard_failure(
    reference: str,
    discord_user_id: str,
    email: str,
    stage: str,
    cause: Exception,
) -> None:
    """Post an onboarding diagnostic without masking the original failure."""
    logger.error(
        "Onboarding failure %s for member %s at %s: %s: %s",
        reference,
        discord_user_id,
        stage,
        type(cause).__name__,
        cause,
    )
    if not settings.DISCORD_SUPPORT_CHANNEL_ID:
        return

    support_mention = (
        f"<@{settings.DISCORD_SUPPORT_USER_ID}> " if settings.DISCORD_SUPPORT_USER_ID else ""
    )
    detail = f"{type(cause).__name__}: {cause}".replace("`", "'")[:1000]
    content = (
        f"{support_mention}**Échec Codaemon** — `{reference}`\n"
        f"Étudiant : <@{discord_user_id}>\n"
        f"Email : `{email}`\n"
        f"Étape : {stage}\n"
        f"Cause : `{detail}`"
    )
    allowed_users = [settings.DISCORD_SUPPORT_USER_ID] if settings.DISCORD_SUPPORT_USER_ID else []

    try:
        with discord.create_client() as client:
            discord.request(
                client,
                "POST",
                discord.channel_messages_route(settings.DISCORD_SUPPORT_CHANNEL_ID),
                {
                    "content": content,
                    "allowed_mentions": {"parse": [], "users": allowed_users},
                },
            )
    except Exception:
        logger.exception("Could not post onboarding failure %s to Discord", reference)
