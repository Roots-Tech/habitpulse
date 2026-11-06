import json
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from habits.services import export_catalog_templates_to_dict


class Command(BaseCommand):
    help = "Exports all catalog templates (predefined & expert) to a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help="Path to output JSON file. Defaults to timestamped file in current directory.",
        )

    def handle(self, *args, **options):
        output_path = options.get("output")
        data = export_catalog_templates_to_dict()

        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        if not output_path:
            output_path = f"catalog_templates_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"

        abs_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully exported {data['template_count']} catalog templates to {abs_path}"
            )
        )
