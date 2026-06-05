"""Onboarding orchestration: bind a Discord member to their learnd student record."""

import logging

from django.conf import settings
from django.core.signing import BadSignature

from bot import discord_actions, learnd
from bot.models import OnboardingLog
from bot.onboarding import read_token

logger = logging.getLogger(__name__)


class OnboardingError(Exception):
    """Raised when onboarding cannot be completed (message shown to the student)."""


def onboard_student(token: str) -> str:
    """Validate the token, bind the member in learnd, apply Discord roles/nickname.

    Returns the member's new nickname. Raises OnboardingError on any user-facing failure.
    """
    try:
        data = read_token(token)
    except BadSignature:
        raise OnboardingError("Lien invalide ou expiré.") from None

    email = data["email"]
    user_id = data["discord_id"]

    domain = email.split("@")[-1]
    if domain not in settings.ALLOWED_EMAIL_DOMAINS:
        raise OnboardingError("Veuillez utiliser une adresse email autorisée.")

    student = learnd.patch_student(email, user_id)
    nickname = f"{student['firstName']} {student['lastName'].upper()}"
    promotion_role_id = student["promotion"]["discord_role_id"]

    discord_actions.apply_onboarding(
        user_id,
        nickname,
        add_role_ids=[settings.DISCORD_BASE_ROLE_ID, promotion_role_id],
        remove_role_ids=[settings.DISCORD_GUEST_ROLE_ID],
    )
    OnboardingLog.objects.create(
        discord_user_id=user_id,
        email=email,
        nickname=nickname,
        promotion_role_id=promotion_role_id,
    )
    logger.info("Onboarded %s as %s", email, nickname)
    return nickname
