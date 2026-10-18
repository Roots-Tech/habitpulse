# Generated manually to wipe habits table data on production/test server

from django.db import migrations


def clear_all_habit_data(apps, schema_editor):
    Habit = apps.get_model("habits", "Habit")
    HabitCompletion = apps.get_model("habits", "HabitCompletion")
    PixelWallet = apps.get_model("habits", "PixelWallet")

    HabitCompletion.objects.all().delete()
    PixelWallet.objects.all().delete()
    Habit.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0009_pixelwallet"),
    ]

    operations = [
        migrations.RunPython(clear_all_habit_data, reverse_code=migrations.RunPython.noop),
    ]
