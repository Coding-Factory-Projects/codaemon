"""Academic-year rollover orchestration between learnd and Discord."""

from collections.abc import Callable

from django.utils.translation import gettext as _

from bot import learnd
from bot.discord_api import categories as discord_categories


def run(dry_run: bool, progress: Callable[[str], None] | None = None) -> str:
    """Archive one year, purge older years, and reconcile the active roster."""
    data = learnd.fetch_rollover()
    active_year = data["active_year"]
    archived_years = sorted(
        data["archived_years"], key=lambda year: year["start_year"], reverse=True
    )
    retained_year = archived_years[0] if archived_years else None
    purged_years = archived_years[1:]

    if dry_run:
        return _format_plan(active_year, retained_year, purged_years)

    if retained_year is not None:
        retained_classes = retained_year["school_classes"]
        for index, school_class in enumerate(retained_classes, start=1):
            _report(
                progress,
                _("Archivage {current}/{total} : {name} - {campus}").format(
                    current=index,
                    total=len(retained_classes),
                    name=school_class["name"],
                    campus=school_class["campus"],
                ),
            )
            discord_categories.archive_class_resources(
                school_class["name"],
                school_class["campus"],
                retained_year["start_year"],
                school_class["discord_role_id"],
                school_class["discord_category_id"],
            )

    purged_classes = [
        (year["start_year"], school_class)
        for year in purged_years
        for school_class in year["school_classes"]
    ]
    for index, (start_year, school_class) in enumerate(purged_classes, start=1):
        _report(
            progress,
            _("Suppression {current}/{total} : {name} - {campus}").format(
                current=index,
                total=len(purged_classes),
                name=school_class["name"],
                campus=school_class["campus"],
            ),
        )
        discord_categories.delete_class_resources(
            school_class["name"],
            school_class["campus"],
            start_year,
            school_class["discord_role_id"],
            school_class["discord_category_id"],
        )

    active_classes = active_year["school_classes"]
    for index, school_class in enumerate(active_classes, start=1):
        _report(
            progress,
            _("Synchronisation {current}/{total} : {name} - {campus}").format(
                current=index,
                total=len(active_classes),
                name=school_class["name"],
                campus=school_class["campus"],
            ),
        )
        role_id, category_id = discord_categories.reconcile_class_category(
            school_class["name"],
            school_class["campus"],
            school_class["discord_role_id"],
            school_class["discord_category_id"],
        )
        if role_id == school_class["discord_role_id"]:
            if category_id == school_class["discord_category_id"]:
                continue
        learnd.patch_school_class_discord_ids(school_class["id"], role_id, category_id)

    retained_count = len(retained_year["school_classes"]) if retained_year else 0
    purged_count = sum(len(year["school_classes"]) for year in purged_years)
    active_count = len(active_year["school_classes"])
    return _(
        "Rollover terminé : {retained} classes archivées, {purged} classes supprimées, "
        "{active} classes actives synchronisées."
    ).format(retained=retained_count, purged=purged_count, active=active_count)


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _format_plan(
    active_year: learnd.RolloverYear,
    retained_year: learnd.RolloverYear | None,
    purged_years: list[learnd.RolloverYear],
) -> str:
    retained_count = len(retained_year["school_classes"]) if retained_year else 0
    purged_count = sum(len(year["school_classes"]) for year in purged_years)
    removed_channels = purged_count * (len(discord_categories.CHANNEL_TEMPLATE) + 1)
    purge_labels = ", ".join(_year_label(year["start_year"]) for year in purged_years)
    if not purge_labels:
        purge_labels = _("aucune")
    return _(
        "Prévisualisation du rollover :\n"
        "- année active {active_year} : {active} classes à synchroniser\n"
        "- année archivée conservée : {retained} classes à renommer\n"
        "- années supprimées : {purge_labels}\n"
        "- suppression estimée : {purged} catégories, {channels} canaux associés et "
        "{purged} rôles"
    ).format(
        active_year=_year_label(active_year["start_year"]),
        active=len(active_year["school_classes"]),
        retained=retained_count,
        purge_labels=purge_labels,
        purged=purged_count,
        channels=removed_channels - purged_count,
    )


def _year_label(start_year: int) -> str:
    return f"{start_year}-{start_year + 1}"
