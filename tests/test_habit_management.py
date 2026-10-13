from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
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
