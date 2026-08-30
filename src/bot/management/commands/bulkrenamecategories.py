import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from bot.discord_api import categories as discord_categories


class Command(BaseCommand):
    help = "Bulk rename same-named Discord categories and roles from a CSV file."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("csv_path", help="CSV file with old_name and new_name columns")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the renames; without this option the command is a dry run",
        )

    def handle(self, *args: object, **options: object) -> None:
        if not settings.DISCORD_TOKEN or not settings.DISCORD_GUILD_ID:
            raise CommandError("DISCORD_TOKEN and DISCORD_GUILD_ID must be set")

        csv_path = options["csv_path"]
        apply = options["apply"]
        if not isinstance(csv_path, str):
            raise CommandError("CSV path must be a string")
        if not isinstance(apply, bool):
            raise CommandError("Apply option must be a boolean")

        renames = _read_renames(Path(csv_path))
        for old_name, new_name in renames:
            self.stdout.write(f"{old_name} -> {new_name}")

        try:
            discord_categories.bulk_rename_categories(renames, apply)
        except discord_categories.CategoryRenameError as exc:
            raise CommandError(str(exc)) from exc

        if apply:
            self.stdout.write(self.style.SUCCESS(f"Renamed {len(renames)} categories and roles."))
            return
        self.stdout.write(
            self.style.WARNING(
                f"Dry run validated {len(renames)} categories and roles; rerun with --apply."
            )
        )


def _read_renames(path: Path) -> list[tuple[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames != ["old_name", "new_name"]:
                raise CommandError("CSV headers must be exactly: old_name,new_name")

            renames = []
            for line_number, row in enumerate(reader, start=2):
                old_name = row["old_name"].strip()
                new_name = row["new_name"].strip()
                if not old_name or not new_name:
                    raise CommandError(f"CSV row {line_number} contains an empty name")
                renames.append((old_name, new_name))
    except OSError as exc:
        raise CommandError(f"Could not read CSV file: {exc}") from exc

    if not renames:
        raise CommandError("CSV file contains no renames")
    return renames
