from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from habits.models import Habit, HabitCompletion
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class DailyTrackingTestCase(TestCase):
    """
    Tests completion and undo actions, duplicate prevention, future-date blocking,
    and schedule invariants.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="david",
            email="david@example.com",
            password="Password123!",
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "David Workspace")
        self.client = Client()
        self.client.login(username="david", password="Password123!")

        self.today = timezone.localdate()
        self.habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Daily Meditation",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today - timedelta(days=5),
        )

    def test_complete_today_habit_success(self):
        """
        Verify marking habit completed for today creates a record.
        """
        complete_url = reverse("habit_complete", kwargs={"pk": self.habit.pk})
        response = self.client.post(complete_url)

        self.assertEqual(response.status_code, 302)
        completion = HabitCompletion.objects.filter(habit=self.habit, completion_date=self.today).first()
        self.assertIsNotNone(completion)
        self.assertEqual(completion.tenant, self.tenant)

    def test_undo_today_completion_success(self):
        """
        Verify undoing completion deletes the today record.
        """
        # Create completion
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=self.habit,
            completion_date=self.today,
        )

        undo_url = reverse("habit_undo_complete", kwargs={"pk": self.habit.pk})
        response = self.client.post(undo_url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=self.habit, completion_date=self.today).exists())

    def test_duplicate_completion_prevention_at_database_level(self):
        """
        Verify unique constraint prevents duplicate completion records for the same habit and date.
        """
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=self.habit,
            completion_date=self.today,
        )

        with self.assertRaises(IntegrityError):
            HabitCompletion.objects.create(
                tenant=self.tenant,
                habit=self.habit,
                completion_date=self.today,
            )

    def test_idempotent_complete_post_does_not_crash(self):
        """
        Verify repeated completion POST calls handle duplicates gracefully without error.
        """
        complete_url = reverse("habit_complete", kwargs={"pk": self.habit.pk})
        resp1 = self.client.post(complete_url)
        self.assertEqual(resp1.status_code, 302)

        resp2 = self.client.post(complete_url)
        self.assertEqual(resp2.status_code, 302)
        self.assertEqual(HabitCompletion.objects.filter(habit=self.habit, completion_date=self.today).count(), 1)

    def test_future_date_completion_is_blocked(self):
        """
        Verify completion for future dates is rejected.
        """
        tomorrow = self.today + timedelta(days=1)
        complete_url = reverse("habit_complete", kwargs={"pk": self.habit.pk})

        response = self.client.post(complete_url, {"date": tomorrow.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=self.habit, completion_date=tomorrow).exists())

        # Also verify at model validation level
        with self.assertRaises(ValidationError):
            completion = HabitCompletion(
                tenant=self.tenant,
                habit=self.habit,
                completion_date=tomorrow,
            )
            completion.clean()

    def test_date_before_start_date_is_blocked(self):
        """
        Verify completion for dates prior to habit start date is rejected.
        """
        prior_date = self.habit.start_date - timedelta(days=1)
        complete_url = reverse("habit_complete", kwargs={"pk": self.habit.pk})

        response = self.client.post(complete_url, {"date": prior_date.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=self.habit, completion_date=prior_date).exists())

    def test_unscheduled_weekday_completion_is_blocked(self):
        """
        Verify that a habit scheduled for specific weekdays cannot be completed on unscheduled days.
        """
        # Create habit scheduled ONLY on tomorrow's weekday
        tomorrow = self.today + timedelta(days=1)
        weekday_habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Weekend Only Habit",
            frequency=Habit.Frequency.WEEKDAYS,
            selected_weekdays=[tomorrow.weekday()],  # today is not scheduled
            start_date=self.today - timedelta(days=5),
        )

        complete_url = reverse("habit_complete", kwargs={"pk": weekday_habit.pk})
        response = self.client.post(complete_url, {"date": self.today.isoformat()})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=weekday_habit, completion_date=self.today).exists())
