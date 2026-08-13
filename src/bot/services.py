"""Onboarding orchestration: bind a Discord member to their learnd student record."""

import logging

import httpx
from django.conf import settings
from django.core.signing import BadSignature
from django.utils.translation import gettext as _

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
        raise OnboardingError(_("Lien invalide ou expiré.")) from None

    email = data["email"].strip().casefold()
    user_id = data["discord_id"]

    domain = email.split("@")[-1]
    if domain not in settings.ALLOWED_EMAIL_DOMAINS:
        raise OnboardingError(_("Veuillez utiliser une adresse email autorisée."))

    try:
        student = learnd.patch_student(email, user_id)
    except learnd.StudentNotFound:
        raise OnboardingError(_("Aucun étudiant ne correspond à cette adresse email.")) from None
    except learnd.LearndError:
        logger.exception("learnd lookup failed for %s", email)
        raise OnboardingError(_("Le service étudiant est temporairement indisponible.")) from None

    try:
        nickname = f"{student['firstName']} {student['lastName'].upper()}"
        if settings.CODAEMON_TEST_MODE:
            promotion_name = student["promotion"]["discord_role_name"]
            role_ids = discord_actions.resolve_test_roles([promotion_name])
            base_role_id = role_ids["Base"]
            guest_role_id = role_ids["Guest"]
            promotion_role_id = role_ids[promotion_name]
        else:
            base_role_id = settings.DISCORD_BASE_ROLE_ID
            guest_role_id = settings.DISCORD_GUEST_ROLE_ID
            promotion_role_id = student["promotion"]["discord_role_id"]

        discord_actions.apply_onboarding(
            user_id,
            nickname,
            add_role_ids=[base_role_id, promotion_role_id],
            remove_role_ids=[guest_role_id],
        )
    except (discord_actions.TestRoleError, httpx.HTTPError):
        logger.exception("Discord onboarding failed for member %s", user_id)
        raise OnboardingError(_("Discord n'a pas pu mettre à jour votre profil.")) from None

    OnboardingLog.objects.create(
        discord_user_id=user_id,
        email=email,
        nickname=nickname,
        promotion_role_id=promotion_role_id,
    )
    logger.info("Onboarded %s as %s", email, nickname)
    return nickname
