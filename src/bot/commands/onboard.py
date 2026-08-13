import asyncio
import logging

import discord
from discord import app_commands
from django.conf import settings
from django.utils.translation import gettext as _

from bot import mail
from bot.commands import has_any_role
from bot.onboarding import make_token

logger = logging.getLogger(__name__)

NO_PERMISSION = _("Tu n'as pas les rôles requis pour lancer cette commande !")


def register(tree: app_commands.CommandTree, guild: discord.Object) -> None:
    @tree.command(
        name="onboard",
        description=_("Reçois un email pour finaliser ton inscription au serveur"),
        guild=guild,
    )
    @app_commands.describe(mail_etudiant=_("Ton adresse email étudiante"))
    async def onboard(interaction: discord.Interaction, mail_etudiant: str) -> None:
        if not has_any_role(
            interaction, settings.DISCORD_GUEST_ROLE_ID, settings.DISCORD_BASE_ROLE_ID
        ):
            await interaction.response.send_message(NO_PERMISSION, ephemeral=True)
            return

        mail_etudiant = mail_etudiant.strip().casefold()
        domain = mail_etudiant.split("@")[-1]
        if domain not in settings.ALLOWED_EMAIL_DOMAINS:
            allowed = " ou ".join(settings.ALLOWED_EMAIL_DOMAINS)
            await interaction.response.send_message(
                _("Vous devez utiliser un email {allowed} !").format(allowed=allowed),
                ephemeral=True,
            )
            return

        token = make_token(interaction.user.id, mail_etudiant)
        link = f"{settings.WEBSITE_BASE_URL.rstrip('/')}/onboard?token={token}"

        if settings.CODAEMON_TEST_MODE:
            await interaction.response.send_message(
                _("Mode test — [confirmer l'inscription]({link})").format(link=link),
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            await asyncio.to_thread(mail.send_onboarding_email, mail_etudiant, link)
        except Exception:
            logger.exception("onboard email failed")
            await interaction.followup.send(
                _("L'email de confirmation n'a pas pu être envoyé."), ephemeral=True
            )
            return

        await interaction.followup.send(
            _("Un email a été envoyé pour confirmer ton inscription."), ephemeral=True
        )
