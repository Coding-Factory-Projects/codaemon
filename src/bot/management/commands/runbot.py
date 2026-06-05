import logging

import discord
from discord import app_commands
from django.conf import settings
from django.core.management.base import BaseCommand

from bot.commands import categories, onboard

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Discord gateway bot (slash commands + events)."

    def handle(self, *args, **options):
        if not settings.DISCORD_TOKEN or not settings.DISCORD_GUILD_ID:
            self.stderr.write("DISCORD_TOKEN and DISCORD_GUILD_ID must be set.")
            return

        intents = discord.Intents.default()
        intents.members = True  # privileged; enable it on the Discord application

        client = discord.Client(intents=intents)
        tree = app_commands.CommandTree(client)
        guild = discord.Object(id=int(settings.DISCORD_GUILD_ID))

        categories.register(tree, guild)
        onboard.register(tree, guild)

        @client.event
        async def on_ready():
            await tree.sync(guild=guild)
            logger.info("codaemon ready as %s", client.user)

        client.run(settings.DISCORD_TOKEN, log_handler=None)
