import asyncio

import discord
from discord import app_commands
from django.conf import settings
from django.utils.translation import gettext as _

from bot import learnd
from bot.slash_commands.permissions import has_any_role

NO_PERMISSION = _("Tu n'as pas les rôles requis pour lancer cette commande !")


def register(tree: app_commands.CommandTree, guild: discord.Object) -> None:
    @tree.command(
        name="status",
        description=_("Affiche l'état des intégrations de codaemon (Admin)"),
        guild=guild,
    )
    async def status(interaction: discord.Interaction) -> None:
        if not has_any_role(interaction, settings.DISCORD_ADMIN_ROLE_ID):
            await interaction.response.send_message(NO_PERMISSION, ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        learnd_status = await asyncio.to_thread(learnd.check_status)
        discord_latency_ms = round(interaction.client.latency * 1000)
        await interaction.followup.send(
            _format_status(learnd_status, discord_latency_ms),
            ephemeral=True,
        )


def _format_status(status: learnd.LearndStatus, discord_latency_ms: int) -> str:
    active_years = status["active_years"]
    active_years_label = "—"
    if active_years is not None:
        active_years_label = ", ".join(str(year) for year in active_years) or _("aucune")

    school_class_count = status["school_class_count"]
    school_class_count_label = "—"
    if school_class_count is not None:
        school_class_count_label = str(school_class_count)

    learnd_url = settings.LEARND_BASE_URL or _("non configurée")
    return _(
        "**Codaemon**\n"
        "Version : `{version}`\n"
        "Environnement : `{environment}`\n"
        "Backend étudiant : `{student_backend}`\n"
        "Envoi d'onboarding : `{onboard_delivery}`\n"
        "Discord : disponible ({discord_latency_ms} ms)\n\n"
        "**learnd.sh**\n"
        "URL : `{learnd_url}`\n"
        "Health : {health}\n"
        "API Bearer : {api}\n"
        "Année(s) active(s) : {active_years}\n"
        "Classes : {school_class_count}"
    ).format(
        version=settings.PROJECT_VERSION,
        environment=settings.PROJECT_ENV,
        student_backend=settings.STUDENT_BACKEND,
        onboard_delivery=settings.ONBOARD_DELIVERY,
        discord_latency_ms=discord_latency_ms,
        learnd_url=learnd_url,
        health=_health_label(status),
        api=_api_label(status),
        active_years=active_years_label,
        school_class_count=school_class_count_label,
    )


def _health_label(status: learnd.LearndStatus) -> str:
    if not status["health_ok"]:
        return _("indisponible")
    return _("disponible ({latency} ms)").format(latency=status["health_latency_ms"])


def _api_label(status: learnd.LearndStatus) -> str:
    labels = {
        "ok": _("disponible"),
        "missing_token": _("token non configuré"),
        "unauthorized": _("token refusé"),
        "unreachable": _("indisponible"),
        "invalid": _("réponse invalide"),
    }
    label = labels[status["api_status"]]
    if status["api_latency_ms"] is None:
        return label
    return _("{label} ({latency} ms)").format(
        label=label,
        latency=status["api_latency_ms"],
    )
