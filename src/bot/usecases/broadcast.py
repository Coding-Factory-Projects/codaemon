"""Validate and synchronously deliver class broadcasts from learnd."""

import httpx
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext as _

from bot.discord_api import client as discord


class BroadcastProviderError(Exception):
    """Discord could not confirm delivery."""


def broadcast(payload: object) -> str:
    """Return the Discord message ID, allowing only the class role to be notified."""
    if not isinstance(payload, dict):
        raise ValidationError(_("Le contenu doit être un objet JSON."))
    channel_id = _discord_id(payload, "discord_text_channel_id")
    role_id = _discord_id(payload, "discord_role_id")
    subject = _string(payload, "subject")
    message = _string(payload, "message")
    sender = payload.get("sender")
    if not isinstance(sender, dict):
        raise ValidationError(_("L’expéditeur doit être un objet JSON."))
    sender_id = _discord_id(sender, "discord_user_id")
    first_name = _string(sender, "first_name", allow_empty=True)
    last_name = _string(sender, "last_name", allow_empty=True)
    full_name = f"{first_name} {last_name}".strip()
    if not full_name:
        raise ValidationError(_("Le nom de l’expéditeur est obligatoire."))
    validate_email(_string(sender, "email"))
    content = f"<@&{role_id}>\n\n**{subject}**\n\n{message}\n\n{full_name} (<@{sender_id}>)"
    if len(content) > 2000:
        raise ValidationError(_("Le message Discord ne doit pas dépasser 2 000 caractères."))

    try:
        with discord.create_client() as client:
            result = discord.request(
                client,
                "POST",
                discord.channel_messages_route(channel_id),
                {
                    "content": content,
                    "allowed_mentions": {
                        "parse": [],
                        "roles": [role_id],
                        "users": [],
                        "replied_user": False,
                    },
                },
            ).json()
        if not isinstance(result, dict):
            raise ValueError("Invalid Discord response")
        message_id = result.get("id")
        if not isinstance(message_id, str):
            raise ValueError("Invalid Discord message ID")
        if not message_id.isascii():
            raise ValueError("Invalid Discord message ID")
        if not message_id.isdecimal():
            raise ValueError("Invalid Discord message ID")
        return message_id
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise BroadcastProviderError(_("L’envoi du message Discord a échoué.")) from exc


def _string(payload: dict, key: str, *, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValidationError(_("Le champ {field} doit être une chaîne.").format(field=key))
    value = value.strip()
    if not allow_empty:
        if not value:
            raise ValidationError(_("Le champ {field} est obligatoire.").format(field=key))
    return value


def _discord_id(payload: dict, key: str) -> str:
    value = _string(payload, key)
    if not value.isascii():
        raise ValidationError(_("Le champ {field} doit être numérique.").format(field=key))
    if not value.isdecimal():
        raise ValidationError(_("Le champ {field} doit être numérique.").format(field=key))
    return value
