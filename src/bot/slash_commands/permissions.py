"""Permission checks shared by Discord slash commands."""

import discord


def has_any_role(interaction: discord.Interaction, *role_ids: str) -> bool:
    """Return whether the interacting member has one of the supplied roles."""
    user_role_ids = {str(role.id) for role in getattr(interaction.user, "roles", [])}
    return any(str(role_id) in user_role_ids for role_id in role_ids if role_id)
