"""Request and complete the student onboard flow."""

import logging
from typing import TypedDict

import httpx
from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature
from django.utils.translation import gettext as _

from bot import email as outbound_email
from bot import learnd
from bot.discord_api import members, testing_roles
from bot.models import OnboardingLog

logger = logging.getLogger(__name__)

SALT = "codaemon.onboarding"
DEFAULT_MAX_AGE = 3600


class OnboardError(Exception):
    """An onboard operation failed with a message suitable for the student."""


class OnboardToken(TypedDict):
    discord_id: str
    email: str


def request_onboard(discord_id: str | int, email: str) -> str | None:
    """Validate an email and send its confirmation link, returning it in test mode."""
    normalized_email = email.strip().casefold()
    domain = normalized_email.split("@")[-1]
    if domain not in settings.ALLOWED_EMAIL_DOMAINS:
        allowed = " ou ".join(settings.ALLOWED_EMAIL_DOMAINS)
        raise OnboardError(_("Vous devez utiliser un email {allowed} !").format(allowed=allowed))

    token = make_token(discord_id, normalized_email)
    link = f"{settings.WEBSITE_BASE_URL.rstrip('/')}/onboard?token={token}"
    if settings.CODAEMON_TEST_MODE:
        return link

    try:
        outbound_email.send_onboard_email(normalized_email, link)
    except Exception:
        logger.exception("onboard email failed")
        raise OnboardError(_("L'email de confirmation n'a pas pu être envoyé.")) from None
    return None


def complete_onboard(token: str) -> str:
    """Bind the member in learnd and apply their Discord nickname and roles."""
    try:
        data = read_token(token)
    except BadSignature:
        raise OnboardError(_("Lien invalide ou expiré.")) from None

    email = data["email"].strip().casefold()
    user_id = data["discord_id"]

    domain = email.split("@")[-1]
    if domain not in settings.ALLOWED_EMAIL_DOMAINS:
        raise OnboardError(_("Veuillez utiliser une adresse email autorisée."))

    try:
        student = learnd.patch_student(email, user_id)
    except learnd.StudentNotFound:
        raise OnboardError(_("Aucun étudiant ne correspond à cette adresse email.")) from None
    except learnd.LearndError:
        logger.exception("learnd lookup failed for %s", email)
        raise OnboardError(_("Le service étudiant est temporairement indisponible.")) from None

    try:
        nickname = f"{student['firstName']} {student['lastName'].upper()}"
        if settings.CODAEMON_TEST_MODE:
            promotion_name = student["promotion"]["discord_role_name"]
            role_ids = testing_roles.resolve_testing_roles([promotion_name])
            base_role_id = role_ids["Base"]
            guest_role_id = role_ids["Guest"]
            promotion_role_id = role_ids[promotion_name]
        else:
            base_role_id = settings.DISCORD_BASE_ROLE_ID
            guest_role_id = settings.DISCORD_GUEST_ROLE_ID
            promotion_role_id = student["promotion"]["discord_role_id"]

        members.apply_onboard(
            user_id,
            nickname,
            add_role_ids=[base_role_id, promotion_role_id],
            remove_role_ids=[guest_role_id],
        )
    except (testing_roles.TestRoleError, httpx.HTTPError):
        logger.exception("Discord onboarding failed for member %s", user_id)
        raise OnboardError(_("Discord n'a pas pu mettre à jour votre profil.")) from None

    OnboardingLog.objects.create(
        discord_user_id=user_id,
        email=email,
        nickname=nickname,
        promotion_role_id=promotion_role_id,
    )
    logger.info("Onboarded %s as %s", email, nickname)
    return nickname


def make_token(discord_id: str | int, email: str) -> str:
    return signing.dumps({"discord_id": str(discord_id), "email": email}, salt=SALT)


def read_token(token: str, max_age: int = DEFAULT_MAX_AGE) -> OnboardToken:
    """Read a valid onboard token or raise ``BadSignature``."""
    return signing.loads(token, salt=SALT, max_age=max_age)
