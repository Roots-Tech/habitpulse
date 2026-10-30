import os
from django.core.management.base import BaseCommand
from accounts.services import seed_admin_accounts, INITIAL_ADMIN_PROFILES


class Command(BaseCommand):
    help = "Seeds or updates baseline administrative accounts on-demand."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            type=str,
            default=os.environ.get("SEED_ADMIN_PASSWORD", "HabitPulse2026!"),
            help="Common initial password for seeded administrative accounts.",
        )
        parser.add_argument(
            "--no-reset",
            action="store_true",
            help="Do not flag seeded accounts to reset password on first login.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        require_reset = not options["no_reset"]
        self.stdout.write(self.style.NOTICE("Seeding baseline administrative accounts..."))

        result = seed_admin_accounts(common_password=password, require_reset=require_reset)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed {result['total']} admin accounts. "
            f"Created: {result['created']}, Updated: {result['updated']}."
        ))
        if require_reset:
            self.stdout.write(self.style.WARNING("Users have been flagged to reset their password on first login."))
