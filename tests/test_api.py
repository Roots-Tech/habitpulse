from datetime import time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from habits.models import Habit, HabitCompletion
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class ApiEndpointsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="api_user",
            email="api@example.com",
            password="Password123!",
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "API Workspace")
        self.today = timezone.localdate()

        self.habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Read 20 pages",
            frequency=Habit.Frequency.DAILY,
            pixel_score=2,
            start_date=self.today,
        )

    def test_unauthenticated_api_access_blocked(self):
        """Unauthenticated requests to API endpoints must return 401."""
        response = self.client.get(reverse("api:dashboard"))
        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.json())

        response = self.client.get(reverse("api:users_list"))
        self.assertEqual(response.status_code, 401)

    def test_dashboard_api_authenticated(self):
        """GET /api/v1/dashboard/ returns complete structured JSON data."""
        self.client.login(username="api@example.com", password="Password123!")
        response = self.client.get(reverse("api:dashboard"))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("summary", data)
        self.assertIn("wallet", data)
        self.assertIn("habits", data)

        self.assertEqual(len(data["habits"]), 1)
        habit_data = data["habits"][0]
        self.assertEqual(habit_data["id"], self.habit.id)
        self.assertEqual(habit_data["name"], "Read 20 pages")
        self.assertTrue(habit_data["is_scheduled_today"])
        self.assertFalse(habit_data["is_completed_today"])

    def test_habit_complete_api_success(self):
        """POST /api/v1/habits/<id>/complete/ marks completion and returns updated metrics."""
        self.client.login(username="api@example.com", password="Password123!")
        url = reverse("api:habit_complete", kwargs={"pk": self.habit.pk})

        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["is_completed_today"])
        self.assertEqual(data["habit_id"], self.habit.id)
        self.assertEqual(data["streaks"]["current_streak"], 1)
        self.assertIn("wallet", data)

        # Database record check
        self.assertTrue(HabitCompletion.objects.filter(habit=self.habit, completion_date=self.today).exists())

    def test_habit_undo_api_success(self):
        """POST /api/v1/habits/<id>/undo/ reverts completion."""
        self.client.login(username="api@example.com", password="Password123!")

        # Create completion
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=self.habit,
            completion_date=self.today,
        )

        undo_url = reverse("api:habit_undo", kwargs={"pk": self.habit.pk})
        response = self.client.post(undo_url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertFalse(data["is_completed_today"])
        self.assertEqual(data["streaks"]["current_streak"], 0)

        self.assertFalse(HabitCompletion.objects.filter(habit=self.habit, completion_date=self.today).exists())

    def test_habit_complete_api_locked_time_window_fails(self):
        """POST /api/v1/habits/<id>/complete/ respects time window constraints."""
        time_habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Night Run",
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(23, 50),
            window_end_time=time(23, 55),
            start_date=self.today,
        )

        self.client.login(username="api@example.com", password="Password123!")
        url = reverse("api:habit_complete", kwargs={"pk": time_habit.pk})

        # Submit at noon (locked)
        from unittest.mock import patch
        noon_dt = timezone.make_aware(
            timezone.datetime(self.today.year, self.today.month, self.today.day, 12, 0, 0)
        )
        with patch("django.utils.timezone.localtime", return_value=noon_dt):
            response = self.client.post(url)
            self.assertEqual(response.status_code, 400)
            data = response.json()
            self.assertFalse(data["success"])
            self.assertIn("Locked", data["error"])

    def test_users_list_api(self):
        """GET /api/v1/users/ returns users directory with pixel scores."""
        self.client.login(username="api@example.com", password="Password123!")
        response = self.client.get(reverse("api:users_list"))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(data["total_count"], 1)

        user_entry = data["users"][0]
        self.assertEqual(user_entry["username"], "api_user")
        self.assertEqual(user_entry["email"], "api@example.com")
        self.assertIn("pixel_score", user_entry)
        self.assertIn("role", user_entry)

    def test_habit_status_api(self):
        """GET /api/v1/habits/<id>/status/ returns real-time status."""
        self.client.login(username="api@example.com", password="Password123!")
        url = reverse("api:habit_status", kwargs={"pk": self.habit.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["id"], self.habit.id)
        self.assertTrue(data["is_scheduled_today"])
        self.assertFalse(data["is_completed_today"])
