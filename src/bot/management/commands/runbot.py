import logging

import discord
import httpx
from discord import app_commands
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from bot import discord_actions, learnd
from bot.commands import categories, onboard

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Discord gateway bot (slash commands + events)."

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DISCORD_TOKEN or not settings.DISCORD_GUILD_ID:
            self.stderr.write("DISCORD_TOKEN and DISCORD_GUILD_ID must be set.")
            return

        if settings.CODAEMON_TEST_MODE:
            try:
                promotion_names = learnd.fixture_promotion_names()
                roles = discord_actions.setup_test_roles(promotion_names)
            except (discord_actions.TestRoleError, learnd.LearndError, httpx.HTTPError) as exc:
                raise CommandError(f"Test setup failed: {exc}") from exc
            role_summary = ", ".join(f"{name}={role_id}" for name, role_id in roles.items())
            self.stdout.write(self.style.WARNING(f"TEST MODE enabled. Roles: {role_summary}"))
        else:
            role_settings = {
                "DISCORD_ADMIN_ROLE_ID": settings.DISCORD_ADMIN_ROLE_ID,
                "DISCORD_BASE_ROLE_ID": settings.DISCORD_BASE_ROLE_ID,
                "DISCORD_GUEST_ROLE_ID": settings.DISCORD_GUEST_ROLE_ID,
                "DISCORD_PRODUCT_OWNERS_ROLE_ID": settings.DISCORD_PRODUCT_OWNERS_ROLE_ID,
            }
            missing_roles = [name for name, value in role_settings.items() if not value]
            if missing_roles:
                self.stderr.write(f"Warning: missing role settings: {', '.join(missing_roles)}")

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
