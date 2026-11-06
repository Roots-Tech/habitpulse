from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("habits", "0017_deduplicate_habit_categories"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="habitcategory",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="habitcategory",
            name="name",
            field=models.CharField(max_length=100, unique=True),
        ),
        migrations.RemoveField(
            model_name="habitcategory",
            name="tenant",
        ),
    ]
