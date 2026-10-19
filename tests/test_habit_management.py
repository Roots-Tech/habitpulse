import threading
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from habits.models import Habit
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class HabitManagementTestCase(TestCase):
    """
    Tests habit creation, editing, scheduling validations, and deactivation.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="clara",
            email="clara@example.com",
            password="Password123!",
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "Clara Workspace")
        self.client = Client()
        self.client.login(username="clara", password="Password123!")
        self.today = timezone.localdate()

    def test_create_daily_habit_success(self):
        """
        Verify successful creation of a daily habit.
        """
        response = self.client.post(reverse("habit_create"), {
            "name": "Drink 2L Water",
            "description": "Stay hydrated throughout the day",
            "category": Habit.Category.HEALTH,
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))

        habit = Habit.objects.filter(tenant=self.tenant, name="Drink 2L Water").first()
        self.assertIsNotNone(habit)
        self.assertEqual(habit.created_by, self.user)
        self.assertEqual(habit.category, Habit.Category.HEALTH)
        self.assertEqual(habit.frequency, Habit.Frequency.DAILY)
        self.assertTrue(habit.is_active)
        # Daily habit scheduled for every day
        self.assertEqual(habit.selected_weekdays, [0, 1, 2, 3, 4, 5, 6])

    def test_create_weekday_habit_success(self):
        """
        Verify successful creation of a weekday-specific habit.
        """
        response = self.client.post(reverse("habit_create"), {
            "name": "Solve 2 DSA Problems",
            "description": "Prepare for coding interviews",
            "category": Habit.Category.LEARNING,
            "frequency": Habit.Frequency.WEEKDAYS,
            "weekdays": ["0", "2", "4"],  # Mon, Wed, Fri
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        habit = Habit.objects.filter(tenant=self.tenant, name="Solve 2 DSA Problems").first()
        self.assertIsNotNone(habit)
        self.assertEqual(habit.frequency, Habit.Frequency.WEEKDAYS)
        self.assertEqual(habit.selected_weekdays, [0, 2, 4])

    def test_create_weekday_habit_without_selected_days_fails(self):
        """
        Verify that frequency=WEEKDAYS without any chosen days triggers validation error.
        """
        response = self.client.post(reverse("habit_create"), {
            "name": "Incomplete Habit",
            "category": Habit.Category.OTHER,
            "frequency": Habit.Frequency.WEEKDAYS,
            "weekdays": [],
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "weekdays", "Please select at least one day of the week.")
        self.assertEqual(Habit.objects.filter(tenant=self.tenant, name="Incomplete Habit").count(), 0)

    def test_edit_habit_details(self):
        """
        Verify updating an existing habit.
        """
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Read 10 pages",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        response = self.client.post(reverse("habit_edit", kwargs={"pk": habit.pk}), {
            "name": "Read 25 pages",
            "description": "Updated goal",
            "category": Habit.Category.PERSONAL_DEV,
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })

        self.assertEqual(response.status_code, 302)
        habit.refresh_from_db()
        self.assertEqual(habit.name, "Read 25 pages")
        self.assertEqual(habit.category, Habit.Category.PERSONAL_DEV)
        self.assertEqual(habit.description, "Updated goal")

    def test_deactivate_and_reactivate_habit(self):
        """
        Verify toggling active status of a habit.
        """
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Gym Workout",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
            is_active=True,
        )

        toggle_url = reverse("habit_toggle_active", kwargs={"pk": habit.pk})

        # Deactivate
        resp1 = self.client.post(toggle_url)
        self.assertEqual(resp1.status_code, 302)
        habit.refresh_from_db()
        self.assertFalse(habit.is_active)

        # Reactivate
        resp2 = self.client.post(toggle_url)
        self.assertEqual(resp2.status_code, 302)
        habit.refresh_from_db()
        self.assertTrue(habit.is_active)

    def test_create_habit_idempotent_multi_click_with_token(self):
        """
        Verify that multiple rapid clicks submitting the same form with an idempotency key
        results in exactly ONE habit being created (strictly idempotent).
        """
        idempotency_key = "test-token-12345"
        payload = {
            "name": "Morning Cold Shower",
            "description": "Boost alertness",
            "category": Habit.Category.HEALTH,
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
            "idempotency_key": idempotency_key,
        }

        # First click
        resp1 = self.client.post(reverse("habit_create"), payload)
        self.assertEqual(resp1.status_code, 302)
        self.assertRedirects(resp1, reverse("dashboard"))

        # Second rapid click (identical payload & token)
        resp2 = self.client.post(reverse("habit_create"), payload)
        self.assertEqual(resp2.status_code, 302)
        self.assertRedirects(resp2, reverse("dashboard"))

        # Third rapid click (identical payload & token)
        resp3 = self.client.post(reverse("habit_create"), payload)
        self.assertEqual(resp3.status_code, 302)
        self.assertRedirects(resp3, reverse("dashboard"))

        # Assert exactly ONE habit was created in DB
        habits = Habit.objects.filter(tenant=self.tenant, name="Morning Cold Shower")
        self.assertEqual(habits.count(), 1)
        self.assertEqual(habits.first().idempotency_key, idempotency_key)

    def test_create_habit_idempotent_rapid_multi_click_without_token(self):
        """
        Verify that even if an idempotency key is omitted, rapid multi-clicks within
        the duplicate window create only ONE habit and redirect cleanly.
        """
        payload = {
            "name": "Evening Stretching",
            "description": "Mobility before sleep",
            "category": Habit.Category.HEALTH,
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        }

        # Rapid clicks without idempotency key
        resp1 = self.client.post(reverse("habit_create"), payload)
        self.assertEqual(resp1.status_code, 302)

        resp2 = self.client.post(reverse("habit_create"), payload)
        self.assertEqual(resp2.status_code, 302)

        # Assert exactly ONE habit created
        self.assertEqual(Habit.objects.filter(tenant=self.tenant, name="Evening Stretching").count(), 1)

    def test_catalog_adoption_idempotent_multi_click(self):
        """
        Verify that clicking 'Add to My Habits' multiple times on a template is strictly idempotent.
        """
        template = Habit.objects.create(
            created_by=self.user,
            name="Circadian Walk 15m",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            pixel_score=5,
            is_active=True,
        )

        adopt_url = reverse("habit_adopt", kwargs={"pk": template.pk})

        # Click 1
        resp1 = self.client.post(adopt_url)
        self.assertEqual(resp1.status_code, 302)

        # Click 2 (duplicate)
        resp2 = self.client.post(adopt_url)
        self.assertEqual(resp2.status_code, 302)

        # Click 3 (duplicate)
        resp3 = self.client.post(adopt_url)
        self.assertEqual(resp3.status_code, 302)

        # Exactly 1 adopted habit in user's workspace
        self.assertEqual(
            Habit.objects.filter(tenant=self.tenant, template_source=template, is_active=True).count(),
            1,
        )

    def test_duplicate_active_habit_creation_later_shows_validation_error(self):
        """
        Verify that attempting to create a duplicate active habit later on (outside the rapid click window)
        provides a clear form validation error.
        """
        # Create an existing habit in the past
        past_habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Read 20 Mins",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today - timedelta(days=2),
            is_active=True,
        )
        # Set created_at to 1 hour ago
        Habit.objects.filter(pk=past_habit.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )

        # User attempts to create a new habit with the same name
        response = self.client.post(reverse("habit_create"), {
            "name": "Read 20 Mins",
            "category": Habit.Category.LEARNING,
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
            "idempotency_key": "new-different-key-999",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "name",
            "An active habit named 'Read 20 Mins' already exists in your workspace.",
        )
        self.assertEqual(Habit.objects.filter(tenant=self.tenant, name="Read 20 Mins").count(), 1)


class ConcurrentHabitCreationTestCase(TransactionTestCase):
    """
    Tests concurrency and race conditions when creating habits with identical idempotency keys.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="concurrent_user",
            email="concurrent@example.com",
            password="Password123!",
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "Concurrent Workspace")
        self.today = timezone.localdate()

    def test_concurrent_habit_creation_identical_idempotency_key(self):
        """
        Verify that multiple concurrent threads attempting to create a habit with the same
        idempotency key result in exactly 1 habit and 0 duplicate rows or crashes.
        """
        idempotency_key = "race-token-xyz-777"
        payload = {
            "name": "Concurrent Habit",
            "category": Habit.Category.HEALTH,
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
            "idempotency_key": idempotency_key,
        }

        results = []
        errors = []

        def worker():
            from django.db import connections
            try:
                c = Client()
                c.login(username="concurrent_user", password="Password123!")
                resp = c.post(reverse("habit_create"), payload)
                results.append(resp.status_code)
            except Exception as e:
                errors.append(e)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors occurred during concurrent creation: {errors}")
        for status in results:
            self.assertEqual(status, 302)

        # Strictly 1 habit in database
        habits = Habit.objects.filter(tenant=self.tenant, name="Concurrent Habit")
        self.assertEqual(habits.count(), 1)
        self.assertEqual(habits.first().idempotency_key, idempotency_key)

