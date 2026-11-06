import os
from django.core.management.base import BaseCommand, CommandError
from habits.services import import_catalog_templates_from_file


class Command(BaseCommand):
    help = "Imports catalog templates from a JSON file into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            nargs="?",
            type=str,
            default="",
            help="Path to JSON file containing templates. Defaults to default_catalog_templates.json.",
        )

    def handle(self, *args, **options):
        file_path = options.get("file_path") or None
        if file_path and not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        result = import_catalog_templates_from_file(file_path=file_path)

        if result.get("errors"):
            for err in result["errors"]:
                self.stderr.write(self.style.ERROR(err))
            raise CommandError("Import completed with errors.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully imported templates: {result['created']} created, {result['updated']} updated (Total: {result['total']})."
            )
        )
