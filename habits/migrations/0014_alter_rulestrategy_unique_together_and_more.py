from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0013_deduplicate_rule_strategies"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="rulestrategy",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="rulestrategy",
            name="name",
            field=models.CharField(max_length=120, unique=True),
        ),
        migrations.RemoveField(
            model_name="rulestrategy",
            name="tenant",
        ),
    ]
