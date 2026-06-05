import asyncio
import logging

import discord
from discord import app_commands
from django.conf import settings

from bot import mail
from bot.commands import has_any_role
from bot.onboarding import make_token

logger = logging.getLogger(__name__)

NO_PERMISSION = "Tu n'as pas les rôles requis pour lancer cette commande !"


def register(tree: app_commands.CommandTree, guild: discord.Object) -> None:
    @tree.command(
        name="onboard",
        description="Reçois un email pour finaliser ton inscription au serveur",
        guild=guild,
    )
    @app_commands.describe(mail_etudiant="Ton adresse email étudiante")
    async def onboard(interaction: discord.Interaction, mail_etudiant: str):
        if not has_any_role(
            interaction, settings.DISCORD_GUEST_ROLE_ID, settings.DISCORD_BASE_ROLE_ID
        ):
            await interaction.response.send_message(NO_PERMISSION, ephemeral=True)
            return

        domain = mail_etudiant.split("@")[-1]
        if domain not in settings.ALLOWED_EMAIL_DOMAINS:
            allowed = " ou ".join(settings.ALLOWED_EMAIL_DOMAINS)
            await interaction.response.send_message(
                f"Vous devez utiliser un email {allowed} !", ephemeral=True
            )
            return

        token = make_token(interaction.user.id, mail_etudiant)
        link = f"{settings.WEBSITE_BASE_URL.rstrip('/')}/onboard?token={token}"
        try:
            await asyncio.to_thread(mail.send_onboarding_email, mail_etudiant, link)
            await interaction.response.send_message(
                "Un email a été envoyé pour confirmer ton inscription.", ephemeral=True
            )
        except Exception:
            logger.exception("onboard email failed")
            await interaction.response.send_message(
                "L'email de confirmation n'a pas pu être envoyé.", ephemeral=True
            )
