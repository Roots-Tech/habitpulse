from django.db import migrations


def deduplicate_and_consolidate_rule_strategies(apps, schema_editor):
    RuleStrategy = apps.get_model("habits", "RuleStrategy")
    Habit = apps.get_model("habits", "Habit")

    # 1. Group strategies by engine_type and normalized name
    all_strategies = list(RuleStrategy.objects.all().order_by("id"))
    canonical_map = {}
    for strat in all_strategies:
        norm_name = strat.name.strip().lower().replace("-", " ")
        key = (strat.engine_type, norm_name)
        if key not in canonical_map:
            canonical_map[key] = strat
        else:
            canonical = canonical_map[key]
            # Re-link any habits referencing the duplicate strategy to the canonical instance
            Habit.objects.filter(rule_strategy_ref=strat).update(rule_strategy_ref=canonical)
            strat.delete()

    # 2. Ensure any remaining name collision is resolved
    remaining = list(RuleStrategy.objects.all().order_by("id"))
    name_map = {}
    for strat in remaining:
        norm_name = strat.name.strip().lower()
        if norm_name not in name_map:
            name_map[norm_name] = strat
        else:
            canonical = name_map[norm_name]
            Habit.objects.filter(rule_strategy_ref=strat).update(rule_strategy_ref=canonical)
            strat.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0012_pixelwallet_bonus_pixels_pixelallocation"),
    ]

    operations = [
        migrations.RunPython(
            deduplicate_and_consolidate_rule_strategies,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
