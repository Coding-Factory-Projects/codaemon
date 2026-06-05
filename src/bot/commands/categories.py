import asyncio
import logging

import discord
from discord import app_commands
from django.conf import settings

from bot import discord_actions
from bot.commands import has_any_role

logger = logging.getLogger(__name__)

NO_PERMISSION = "Tu n'as pas les rôles requis pour lancer cette commande !"


def register(tree: app_commands.CommandTree, guild: discord.Object) -> None:
    @tree.command(
        name="createcategory",
        description="Crée une nouvelle catégorie privée et ses canaux (Admin)",
        guild=guild,
    )
    @app_commands.describe(name="Nom de la catégorie")
    async def createcategory(interaction: discord.Interaction, name: str):
        if not has_any_role(interaction, settings.DISCORD_ADMIN_ROLE_ID):
            await interaction.response.send_message(NO_PERMISSION, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            await asyncio.to_thread(discord_actions.create_category, name)
            await interaction.followup.send(f"La catégorie « {name} » a été créée.")
        except Exception:
            logger.exception("createcategory failed")
            await interaction.followup.send("Une erreur s'est produite !")

    @tree.command(
        name="deletecategory",
        description="Supprime une catégorie et tous ses canaux (Admin)",
        guild=guild,
    )
    @app_commands.describe(channel_id="L'identifiant de la catégorie à supprimer")
    async def deletecategory(interaction: discord.Interaction, channel_id: str):
        if not has_any_role(interaction, settings.DISCORD_ADMIN_ROLE_ID):
            await interaction.response.send_message(NO_PERMISSION, ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            await asyncio.to_thread(discord_actions.delete_category, channel_id)
            await interaction.followup.send("La catégorie a été supprimée.")
        except Exception:
            logger.exception("deletecategory failed")
            await interaction.followup.send("Une erreur s'est produite !")
