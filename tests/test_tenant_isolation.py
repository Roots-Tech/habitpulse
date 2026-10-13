from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from habits.models import Habit, HabitCompletion
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class TenantIsolationTestCase(TestCase):
    """
    Validates strict multi-tenant isolation, URL tampering defenses,
    and prevention of cross-tenant record creation.
    """

    def setUp(self):
        # Create User A and Tenant A
        self.user_a = User.objects.create_user(
            username="user_a",
            email="usera@example.com",
            password="Password123!",
        )
        self.tenant_a, _ = create_personal_workspace_for_user(self.user_a, "Tenant A Workspace")

        # Create User B and Tenant B
        self.user_b = User.objects.create_user(
            username="user_b",
            email="userb@example.com",
            password="Password123!",
        )
        self.tenant_b, _ = create_personal_workspace_for_user(self.user_b, "Tenant B Workspace")

        # Create Habit owned by Tenant A
        self.today = timezone.localdate()
        self.habit_a = Habit.objects.create(
            tenant=self.tenant_a,
            created_by=self.user_a,
            name="Tenant A Secret Habit",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        # Clients
        self.client_a = Client()
        self.client_a.login(username="user_a", password="Password123!")

        self.client_b = Client()
        self.client_b.login(username="user_b", password="Password123!")

    def test_user_b_cannot_view_or_edit_user_a_habit(self):
        """
        User B attempting to view or edit User A's habit must receive a 404 (not found).
        """
        edit_url = reverse("habit_edit", kwargs={"pk": self.habit_a.pk})

        # GET edit form
        resp = self.client_b.get(edit_url)
        self.assertEqual(resp.status_code, 404)

        # POST edit form
        resp = self.client_b.post(edit_url, {
            "name": "Hacked Habit Name",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today,
            "is_active": True,
        })
        self.assertEqual(resp.status_code, 404)

        # Verify Habit A was unchanged
        self.habit_a.refresh_from_db()
        self.assertEqual(self.habit_a.name, "Tenant A Secret Habit")

    def test_user_b_cannot_view_user_a_calendar_or_stats(self):
        """
        User B attempting to view User A's calendar or stats must receive a 404.
        """
        cal_url = reverse("habit_calendar", kwargs={"pk": self.habit_a.pk})
        stats_url = reverse("habit_stats", kwargs={"pk": self.habit_a.pk})

        resp_cal = self.client_b.get(cal_url)
        self.assertEqual(resp_cal.status_code, 404)

        resp_stats = self.client_b.get(stats_url)
        self.assertEqual(resp_stats.status_code, 404)

    def test_user_b_cannot_toggle_user_a_habit_active_status(self):
        """
        User B attempting to toggle active status of User A's habit must receive a 404.
        """
        toggle_url = reverse("habit_toggle_active", kwargs={"pk": self.habit_a.pk})
        resp = self.client_b.post(toggle_url)
        self.assertEqual(resp.status_code, 404)

        self.habit_a.refresh_from_db()
        self.assertTrue(self.habit_a.is_active)

    def test_user_b_cannot_complete_or_undo_user_a_habit(self):
        """
        User B attempting to mark complete or undo User A's habit must receive a 404.
        """
        complete_url = reverse("habit_complete", kwargs={"pk": self.habit_a.pk})
        undo_url = reverse("habit_undo_complete", kwargs={"pk": self.habit_a.pk})

        resp_complete = self.client_b.post(complete_url)
        self.assertEqual(resp_complete.status_code, 404)
        self.assertEqual(HabitCompletion.objects.filter(habit=self.habit_a).count(), 0)

        # User A completes it
        self.client_a.post(complete_url)
        self.assertEqual(HabitCompletion.objects.filter(habit=self.habit_a).count(), 1)

        # User B attempts undo
        resp_undo = self.client_b.post(undo_url)
        self.assertEqual(resp_undo.status_code, 404)
        self.assertEqual(HabitCompletion.objects.filter(habit=self.habit_a).count(), 1)

    def test_cross_tenant_completion_invariant_enforced(self):
        """
        Ensures that creating a completion record with mismatched tenant and habit
        raises a validation error at model validation.
        """
        mismatched_completion = HabitCompletion(
            tenant=self.tenant_b,  # Tenant B
            habit=self.habit_a,    # Habit belongs to Tenant A
            completion_date=self.today,
        )
        with self.assertRaises(ValidationError):
            mismatched_completion.clean()

    def test_dashboard_does_not_leak_cross_tenant_habits(self):
        """
        User B's dashboard must only list Tenant B habits, never Tenant A habits.
        """
        # Create habit for Tenant B
        habit_b = Habit.objects.create(
            tenant=self.tenant_b,
            created_by=self.user_b,
            name="Tenant B Morning Jog",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        resp = self.client_b.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Tenant B Morning Jog")
        self.assertNotContains(resp, "Tenant A Secret Habit")
