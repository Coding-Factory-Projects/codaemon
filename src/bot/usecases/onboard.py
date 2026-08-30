"""Request and complete the student onboard flow."""

import logging
import secrets
from typing import TypedDict

import httpx
from django.conf import settings
from django.core import signing
from django.core.signing import BadSignature
from django.utils.translation import gettext as _

from bot import email as outbound_email
from bot import learnd
from bot.discord_api import members, support, testing_roles
from bot.models import OnboardingLog
from config.constants import OnboardDelivery, StudentBackend

logger = logging.getLogger(__name__)

SALT = "codaemon.onboarding"
DEFAULT_MAX_AGE = 3600


class OnboardError(Exception):
    """An onboard operation failed with a message suitable for the student."""


class OnboardToken(TypedDict):
    discord_id: str
    email: str


def request_onboard(discord_id: str | int, email: str) -> str | None:
    """Validate an email and deliver its confirmation link as configured."""
    normalized_email = email.strip().casefold()
    domain = normalized_email.split("@")[-1]
    if domain not in settings.ALLOWED_EMAIL_DOMAINS:
        allowed = " ou ".join(settings.ALLOWED_EMAIL_DOMAINS)
        raise OnboardError(_("Vous devez utiliser un email {allowed} !").format(allowed=allowed))

    token = make_token(discord_id, normalized_email)
    link = f"{settings.WEBSITE_BASE_URL.rstrip('/')}/onboard?token={token}"
    if settings.ONBOARD_DELIVERY == OnboardDelivery.LINK:
        return link

    try:
        outbound_email.send_onboard_email(normalized_email, link)
    except Exception as exc:
        logger.exception("onboard email failed")
        raise _reported_error(
            discord_id=str(discord_id),
            email=normalized_email,
            stage="envoi de l'email",
            student_message=_("Codaemon n'a pas pu envoyer l'email de confirmation."),
            cause=exc,
        ) from None
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
        student = learnd.onboard_student(email, user_id)
    except learnd.StudentNotFound:
        raise OnboardError(_("Aucun étudiant ne correspond à cette adresse email.")) from None
    except learnd.LearndError as exc:
        logger.exception("learnd lookup failed for %s", email)
        raise _reported_error(
            discord_id=user_id,
            email=email,
            stage="service étudiant",
            student_message=_("Codaemon n'a pas pu contacter le service étudiant."),
            cause=exc,
        ) from None

    try:
        nickname = f"{student['first_name']} {student['last_name'].upper()}"
        if settings.STUDENT_BACKEND == StudentBackend.FIXTURE:
            promotion_name = student["discord_role_id"]
            role_ids = testing_roles.resolve_testing_roles([promotion_name])
            base_role_id = role_ids["Base"]
            guest_role_id = role_ids["Guest"]
            promotion_role_id = role_ids[promotion_name]
        else:
            base_role_id = settings.DISCORD_BASE_ROLE_ID
            guest_role_id = settings.DISCORD_GUEST_ROLE_ID
            promotion_role_id = student["discord_role_id"]

        members.apply_onboard(
            user_id,
            nickname,
            add_role_ids=[base_role_id, promotion_role_id],
            remove_role_ids=[guest_role_id],
        )
    except (testing_roles.TestRoleError, httpx.HTTPError) as exc:
        logger.exception("Discord onboarding failed for member %s", user_id)
        raise _reported_error(
            discord_id=user_id,
            email=email,
            stage="mise à jour Discord",
            student_message=_("Codaemon n'a pas pu mettre à jour ton profil Discord."),
            cause=exc,
        ) from None

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


def _reported_error(
    discord_id: str,
    email: str,
    stage: str,
    student_message: str,
    cause: Exception,
) -> OnboardError:
    reference = f"CODAEMON-{secrets.token_hex(3).upper()}"
    support.report_onboard_failure(reference, discord_id, email, stage, cause)
    return OnboardError(
        _("{message} Un administrateur a été prévenu. Erreur : {reference}").format(
            message=student_message,
            reference=reference,
        )
    )
