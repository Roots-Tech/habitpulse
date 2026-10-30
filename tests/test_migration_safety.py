import importlib
import inspect
from django.db import migrations
from django.test import TestCase


class MigrationSafetyTestCase(TestCase):
    """
    Test suite verifying that migration 0010 has been safely neutralized
    and contains zero destructive database operations (SEC-06).
    """

    def test_migration_0010_is_noop(self):
        """
        Asserts that migration 0010 uses RunPython.noop and contains no destructive table deletes.
        """
        migration_0010 = importlib.import_module("habits.migrations.0010_clear_all_habits_on_production")
        migration = migration_0010.Migration("0010_clear_all_habits_on_production", "habits")
        self.assertEqual(len(migration.operations), 1)

        op = migration.operations[0]
        self.assertIsInstance(op, migrations.RunPython)
        self.assertEqual(op.code, migrations.RunPython.noop)
        self.assertEqual(op.reverse_code, migrations.RunPython.noop)

        # Confirm that dangerous delete calls are not in the module
        source = inspect.getsource(migration_0010)
        self.assertNotIn(".delete()", source)
        self.assertNotIn("clear_all_habit_data", source)
