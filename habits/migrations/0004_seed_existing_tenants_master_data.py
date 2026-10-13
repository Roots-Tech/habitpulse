from django.db import migrations


def seed_existing_tenants(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    HabitCategory = apps.get_model("habits", "HabitCategory")
    RuleStrategy = apps.get_model("habits", "RuleStrategy")

    default_categories = [
        {"name": "Health", "icon": "🍎", "color": "#10b981", "description": "Physical health, nutrition, and well-being."},
        {"name": "Fitness", "icon": "🏋️", "color": "#f59e0b", "description": "Exercise, workouts, and athletic training."},
        {"name": "Learning", "icon": "📚", "color": "#6366f1", "description": "Reading, studying, coding, and skill development."},
        {"name": "Productivity", "icon": "⚡", "color": "#3b82f6", "description": "Work habits, focus routines, and organization."},
        {"name": "Personal Development", "icon": "🌱", "color": "#ec4899", "description": "Mindfulness, meditation, journaling, and self-improvement."},
        {"name": "Other", "icon": "📌", "color": "#8b5cf6", "description": "General habits and hobbies."},
    ]

    default_rules = [
        {
            "name": "Honor System (One-Click)",
            "engine_type": "STANDARD",
            "description": "Standard honor system. Check off habit with a single tap.",
        },
        {
            "name": "Time Window Constrained",
            "engine_type": "TIME_WINDOW",
            "description": "Can only be completed within a defined daily time window.",
        },
        {
            "name": "Proof Required (Image/Doc)",
            "engine_type": "EVIDENCE_FILE",
            "description": "Requires uploading an image or document as proof of completion.",
        },
        {
            "name": "Quantitative Goal",
            "engine_type": "NUMERIC_TARGET",
            "description": "Requires logging a numeric value that reaches or exceeds your target.",
        },
        {
            "name": "Time Window + Proof Required",
            "engine_type": "TIME_AND_EVIDENCE",
            "description": "Requires completing within a time window AND uploading proof.",
        },
    ]

    for tenant in Tenant.objects.all():
        for cat in default_categories:
            HabitCategory.objects.get_or_create(
                tenant=tenant,
                name=cat["name"],
                defaults={
                    "icon": cat["icon"],
                    "color": cat["color"],
                    "description": cat["description"],
                    "is_active": True,
                },
            )
        for rule in default_rules:
            RuleStrategy.objects.get_or_create(
                tenant=tenant,
                name=rule["name"],
                defaults={
                    "engine_type": rule["engine_type"],
                    "description": rule["description"],
                    "is_active": True,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ('habits', '0003_alter_habit_category_rulestrategy_habitcategory_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_existing_tenants, migrations.RunPython.noop),
    ]
