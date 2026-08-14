import asyncio
import logging

import discord
from discord import app_commands
from django.conf import settings
from django.utils.translation import gettext as _

from bot import rollover as rollover_service
from bot.commands import has_any_role

logger = logging.getLogger(__name__)


def register(tree: app_commands.CommandTree, guild: discord.Object) -> None:
    @tree.command(
        name="rollover",
        description=_("Archive l'année précédente et synchronise la nouvelle année"),
        guild=guild,
    )
    @app_commands.describe(dry_run=_("Prévisualiser les changements sans les appliquer"))
    async def rollover(interaction: discord.Interaction, dry_run: bool = True) -> None:
        if not has_any_role(interaction, settings.DISCORD_ADMIN_ROLE_ID):
            await interaction.response.send_message(
                _("Tu n'as pas les rôles requis pour lancer cette commande !"), ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        loop = asyncio.get_running_loop()

        def report_progress(message: str) -> None:
            future = asyncio.run_coroutine_threadsafe(
                interaction.edit_original_response(content=message), loop
            )
            try:
                future.result()
            except Exception:
                logger.warning("could not update rollover progress", exc_info=True)

        try:
            result = await asyncio.to_thread(rollover_service.run, dry_run, report_progress)
        except Exception:
            logger.exception("rollover failed")
            await interaction.edit_original_response(
                content=_("Le rollover a échoué. Consulte les logs avant de réessayer.")
            )
            return
        await interaction.edit_original_response(content=result)
