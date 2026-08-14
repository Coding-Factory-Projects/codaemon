import asyncio
import logging

import discord
import httpx
from discord import app_commands
from django.conf import settings
from django.utils.translation import gettext as _

from bot import discord_actions, learnd, mail
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

    if not settings.CODAEMON_TEST_MODE:
        return

    @tree.command(
        name="resetmember",
        description=_("Réinitialise un membre pour tester à nouveau son inscription"),
        guild=guild,
    )
    @app_commands.describe(member=_("Le membre à réinitialiser"))
    async def resetmember(interaction: discord.Interaction, member: discord.Member) -> None:
        if not has_any_role(interaction, settings.DISCORD_ADMIN_ROLE_ID):
            await interaction.response.send_message(NO_PERMISSION, ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            promotion_names = learnd.fixture_promotion_names()
            await asyncio.to_thread(
                discord_actions.reset_test_member,
                str(member.id),
                promotion_names,
            )
        except (discord_actions.TestRoleError, learnd.LearndError, httpx.HTTPError):
            logger.exception("resetmember failed")
            await interaction.followup.send(
                _("Le membre n'a pas pu être réinitialisé."), ephemeral=True
            )
            return

        await interaction.followup.send(
            _("{member} peut recommencer son inscription.").format(member=member.mention),
            ephemeral=True,
        )
