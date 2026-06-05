import discord


def has_any_role(interaction: discord.Interaction, *role_ids: str) -> bool:
    """True if the interacting member has at least one of the given role ids."""
    user_role_ids = {str(r.id) for r in getattr(interaction.user, "roles", [])}
    return any(str(rid) in user_role_ids for rid in role_ids if rid)
