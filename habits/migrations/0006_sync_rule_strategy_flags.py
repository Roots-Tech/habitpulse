from django.db import migrations


def sync_rule_strategy_flags(apps, schema_editor):
    RuleStrategy = apps.get_model("habits", "RuleStrategy")
    
    # 1. NUMERIC_TARGET
    RuleStrategy.objects.filter(engine_type="NUMERIC_TARGET").update(
        requires_numeric=True,
        has_time_window=False,
        requires_evidence=False,
    )
    
    # 2. TIME_WINDOW
    RuleStrategy.objects.filter(engine_type="TIME_WINDOW").update(
        has_time_window=True,
        requires_numeric=False,
        requires_evidence=False,
    )
    
    # 3. TIME_AND_EVIDENCE
    RuleStrategy.objects.filter(engine_type="TIME_AND_EVIDENCE").update(
        has_time_window=True,
        requires_evidence=True,
        requires_numeric=False,
    )
    
    # 4. EVIDENCE_FILE
    RuleStrategy.objects.filter(engine_type="EVIDENCE_FILE").update(
        requires_evidence=True,
        has_time_window=False,
        requires_numeric=False,
    )
    
    # 5. STANDARD
    RuleStrategy.objects.filter(engine_type="STANDARD").update(
        has_time_window=False,
        requires_numeric=False,
        requires_evidence=False,
    )


def reverse_sync(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0005_habit_habit_type_habit_is_template_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_rule_strategy_flags, reverse_code=reverse_sync),
    ]
