import asyncio
import logging

import discord
import httpx
from discord import app_commands
from django.conf import settings
from django.utils.translation import gettext as _

from bot import learnd
from bot.discord_api import members, testing_roles
from bot.slash_commands.permissions import has_any_role
from bot.usecases.onboard import OnboardError, request_onboard
from config.constants import StudentBackend

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

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            link = await asyncio.to_thread(request_onboard, interaction.user.id, mail_etudiant)
        except OnboardError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        if link is not None:
            await interaction.followup.send(
                _("Mode test — [confirmer l'inscription]({link})").format(link=link),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            _("Un email a été envoyé pour confirmer ton inscription."), ephemeral=True
        )

    if settings.PROJECT_ENV == "prod":
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
            if settings.STUDENT_BACKEND == StudentBackend.FIXTURE:
                promotion_names = learnd.fixture_promotion_names()
                role_ids = testing_roles.resolve_testing_roles(promotion_names)
                promotion_role_ids = [role_ids[name] for name in promotion_names]
            else:
                rollover = learnd.fetch_rollover()
                promotion_role_ids = [
                    school_class["discord_role_id"]
                    for school_class in rollover["active_year"]["school_classes"]
                    if school_class["discord_role_id"]
                ]
            await asyncio.to_thread(
                members.reset_member,
                str(member.id),
                promotion_role_ids,
            )
        except (testing_roles.TestRoleError, learnd.LearndError, httpx.HTTPError):
            logger.exception("resetmember failed")
            await interaction.followup.send(
                _("Le membre n'a pas pu être réinitialisé."), ephemeral=True
            )
            return

        await interaction.followup.send(
            _("{member} peut recommencer son inscription.").format(member=member.mention),
            ephemeral=True,
        )
