from django.core.management.base import BaseCommand
from habits.models import Habit, HabitCompletion, PixelWallet


class Command(BaseCommand):
    help = "Clears all habit data (User Defined, Predefined Purposeful, and Expert Prescribed), including completions and pixel wallets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-templates",
            action="store_true",
            help="Keep catalog template definitions and only delete user-assigned habits.",
        )

    def handle(self, *args, **options):
        keep_templates = options.get("keep_templates", False)

        if keep_templates:
            habits_to_delete = Habit.objects.filter(is_template=False)
            label = "user habits (excluding templates)"
        else:
            habits_to_delete = Habit.objects.all()
            label = "all habits (user-defined, predefined, expert-prescribed, and templates)"

        habit_count = habits_to_delete.count()
        completion_count = HabitCompletion.objects.count()
        wallet_count = PixelWallet.objects.count()

        # Clear completions and pixel wallets
        HabitCompletion.objects.all().delete()
        PixelWallet.objects.all().delete()
        habits_to_delete.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully cleared {label}: "
                f"{habit_count} habits, {completion_count} completions, {wallet_count} pixel wallets."
            )
        )
