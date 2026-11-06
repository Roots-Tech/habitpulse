from django.db import migrations


def deduplicate_and_consolidate_habit_categories(apps, schema_editor):
    HabitCategory = apps.get_model("habits", "HabitCategory")
    Habit = apps.get_model("habits", "Habit")

    # 1. Group categories by normalized name
    all_categories = list(HabitCategory.objects.all().order_by("id"))
    canonical_map = {}

    # First pass: map canonicals, prefer ones that already have habits linked to them
    for cat in all_categories:
        norm_name = cat.name.strip().lower()
        if norm_name not in canonical_map:
            canonical_map[norm_name] = cat
        else:
            current_canonical = canonical_map[norm_name]
            current_has_habits = Habit.objects.filter(category_ref=current_canonical).exists()
            this_has_habits = Habit.objects.filter(category_ref=cat).exists()
            if not current_has_habits and this_has_habits:
                canonical_map[norm_name] = cat

    # Second pass: re-link habits from duplicate categories to canonical instance and remove duplicates
    for cat in all_categories:
        norm_name = cat.name.strip().lower()
        canonical = canonical_map[norm_name]
        if cat.id != canonical.id:
            # Re-link any habits referencing the duplicate category to the canonical instance
            Habit.objects.filter(category_ref=cat).update(category_ref=canonical, category=canonical.name)
            cat.delete()

    # Third pass: re-link any habits where category_ref is null but category string matches canonical name
    for norm_name, canonical in canonical_map.items():
        Habit.objects.filter(category_ref__isnull=True, category__iexact=canonical.name).update(
            category_ref=canonical,
            category=canonical.name
        )


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0016_pixelrewardconfig"),
    ]

    operations = [
        migrations.RunPython(
            deduplicate_and_consolidate_habit_categories,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
