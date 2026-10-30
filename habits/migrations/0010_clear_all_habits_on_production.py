# Neutralized migration (SEC-06):
# Previously contained destructive calls to purge Habit, HabitCompletion, and PixelWallet records.
# Neutralized with migrations.RunPython.noop to preserve the migration dependency chain
# while guaranteeing strict data retention and zero data loss across all environments.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0009_pixelwallet"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, reverse_code=migrations.RunPython.noop),
    ]
