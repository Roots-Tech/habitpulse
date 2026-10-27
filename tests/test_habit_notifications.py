from datetime import date, time, timedelta, datetime
from unittest.mock import patch
from django.test import TestCase, Client, RequestFactory
from django.utils import timezone

from accounts.models import User
from tenants.models import Membership, Tenant
from habits.models import Habit, HabitCompletion
from habits.context_processors import habit_notifications


class HabitNotificationsTests(TestCase):
    """
    Tests for the habit alarm notifications context processor and bell icon rendering:
    - Removal of completed habits from the notification panel once marked complete
    - Midnight rollover: fresh pending habits shown at the start of the next day
    - Strict operational ordering of notifications based on how they can be completed:
      1. Open right now (earliest closing deadline first)
      2. All-day / Due today (highest pixel reward first)
      3. Upcoming time windows (opening chronologically earliest first)
    - Bell icon without text, unread badge, and point-by-point flyout panel
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="test_notifier",
            email="notifier@example.com",
            password="Password123!",
        )
        self.tenant = Tenant.objects.create(
            name="Notification Workspace",
            slug="notif-ws",
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role="OWNER",
            status="ACTIVE",
        )
        self.client = Client(SERVER_NAME="127.0.0.1")
        self.factory = RequestFactory()

    def test_anonymous_user_returns_empty_notifications(self):
        """Anonymous requests receive an empty notification list and 0 unread alarms."""
        request = self.factory.get("/")
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()

        context = habit_notifications(request)
        self.assertEqual(context["habit_notifications"], [])
        self.assertEqual(context["unread_alarms_count"], 0)
        self.assertFalse(context["has_urgent_alarms"])

    def test_upcoming_habit_notification_message_and_consequence(self):
        """
        Verify exact dynamic message and consequence text for upcoming habit with time window:
        - Calculates login time 5 mins before start time
        - Dynamic habit name, date, and pixel count
        - Specific consequence penalty warning
        """
        today = timezone.localdate()
        fake_now = timezone.make_aware(datetime.combine(today, time(9, 0, 0)))

        future_start = time(10, 0)
        future_end = time(11, 0)
        start_str = "10:00 AM"
        prep_str = "09:55 AM"
        end_str = "11:00 AM"

        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="drink water",
            description="Daily hydration habit",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=5),
            is_active=True,
            window_start_time=future_start,
            window_end_time=future_end,
            habit_type=Habit.HabitType.GENERAL,
        )

        request = self.factory.get("/")
        request.user = self.user
        request.tenant = self.tenant

        with patch("django.utils.timezone.localtime", return_value=fake_now):
            context = habit_notifications(request)

        notifs = context["habit_notifications"]
        self.assertEqual(len(notifs), 1)

        item = notifs[0]
        self.assertEqual(item["habit_name"], "drink water")
        self.assertEqual(item["pixel_score"], 2)
        self.assertEqual(item["prep_time_str"], prep_str)
        self.assertEqual(item["start_time_str"], start_str)
        self.assertEqual(item["end_time_str"], end_str)

        self.assertIn("To ensure you preserve 2 pixels allowed for drink water habit", item["message"])
        self.assertIn(f"login 5 mins before {start_str} (by {prep_str})", item["message"])
        self.assertIn("maintain the consistency streak of a progressive habit", item["message"])

        self.assertIn(f"If you fail to complete the assignment completion before {end_str}", item["consequence"])
        self.assertIn("your consistency to habit will be marked as not completed for the day and your 2 pixel goes off your wallet", item["consequence"])

    def test_open_habit_triggers_urgent_alarms(self):
        """When current time falls inside habit time window, it is open with urgent alarms."""
        today = timezone.localdate()
        fake_now = timezone.make_aware(datetime.combine(today, time(10, 15, 0)))
        open_start = time(10, 0)
        open_end = time(11, 0)

        Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="run",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=3),
            is_active=True,
            window_start_time=open_start,
            window_end_time=open_end,
            habit_type=Habit.HabitType.GENERAL,
        )

        request = self.factory.get("/")
        request.user = self.user
        request.tenant = self.tenant

        with patch("django.utils.timezone.localtime", return_value=fake_now):
            context = habit_notifications(request)

        self.assertEqual(context["unread_alarms_count"], 1)
        self.assertTrue(context["has_urgent_alarms"])

        item = context["habit_notifications"][0]
        self.assertEqual(item["status"], "open")
        self.assertIn("CRITICAL ACTION REQUIRED", item["headline"])

    def test_completed_habit_removed_from_notification_panel(self):
        """
        Requirement: Once a habit is marked complete, remove that notification from the notification panel.
        Panel reflects 0 unread alarms, and completed_today_count tracks the completion.
        """
        today = timezone.localdate()
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="read books",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=2),
            is_active=True,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
        )
        # Mark habit completed for today
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=habit,
            completion_date=today,
        )

        request = self.factory.get("/")
        request.user = self.user
        request.tenant = self.tenant

        context = habit_notifications(request)
        # Completed habit is removed from notification panel
        self.assertEqual(context["habit_notifications"], [])
        self.assertEqual(context["unread_alarms_count"], 0)
        self.assertEqual(context["completed_today_count"], 1)

    def test_next_day_midnight_rollover_shows_pending_habits(self):
        """
        Requirement: At the very first second of the next day, start showing the notification
        of pending habits of the day and clear the completed ones.
        """
        day1 = timezone.localdate()
        day2 = day1 + timedelta(days=1)

        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="daily meditation",
            frequency=Habit.Frequency.DAILY,
            start_date=day1 - timedelta(days=1),
            is_active=True,
            habit_type=Habit.HabitType.GENERAL,
        )
        # Completed on day1
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=habit,
            completion_date=day1,
        )

        request = self.factory.get("/")
        request.user = self.user
        request.tenant = self.tenant

        # On day1: habit is completed, so it is removed from panel
        with patch("django.utils.timezone.localdate", return_value=day1):
            context_day1 = habit_notifications(request)
            self.assertEqual(len(context_day1["habit_notifications"]), 0)
            self.assertEqual(context_day1["unread_alarms_count"], 0)

        # On day2 (very first second of the next day):
        # habit is not yet completed for day2, so it re-appears as pending!
        with patch("django.utils.timezone.localdate", return_value=day2):
            context_day2 = habit_notifications(request)
            self.assertEqual(len(context_day2["habit_notifications"]), 1)
            self.assertEqual(context_day2["unread_alarms_count"], 1)
            self.assertEqual(context_day2["habit_notifications"][0]["habit_name"], "daily meditation")

    def test_notifications_displayed_in_correct_completion_order(self):
        """
        Requirement: Ensure notifications are displayed in correct order of how it can be marked completed:
        1. Open window right now (closest closing deadline first)
        2. All-day habits (available now, sorted by highest pixel stake)
        3. Upcoming windows (opening chronologically earliest first)
        """
        today = timezone.localdate()
        fake_now = timezone.make_aware(datetime.combine(today, time(10, 0, 0)))

        # Habit 1: Open now, closes at 10:15
        h_open_soon = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="open closes in 10m",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=1),
            is_active=True,
            window_start_time=time(9, 45),
            window_end_time=time(10, 15),
            habit_type=Habit.HabitType.GENERAL,
        )

        # Habit 2: Open now, closes at 10:45
        h_open_later = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="open closes in 40m",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=1),
            is_active=True,
            window_start_time=time(9, 45),
            window_end_time=time(10, 45),
            habit_type=Habit.HabitType.GENERAL,
        )

        # Habit 3: All-day due today (5 pixels)
        h_all_day_5 = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="all day 5px",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=1),
            is_active=True,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
        )

        # Habit 4: Upcoming, opens at 11:00
        h_up_1h = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="upcoming in 1h",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=1),
            is_active=True,
            window_start_time=time(11, 0),
            window_end_time=time(12, 0),
            habit_type=Habit.HabitType.GENERAL,
        )

        # Habit 5: Upcoming, opens at 13:00
        h_up_3h = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="upcoming in 3h",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=1),
            is_active=True,
            window_start_time=time(13, 0),
            window_end_time=time(14, 0),
            habit_type=Habit.HabitType.GENERAL,
        )

        request = self.factory.get("/")
        request.user = self.user
        request.tenant = self.tenant

        with patch("django.utils.timezone.localtime", return_value=fake_now):
            context = habit_notifications(request)

        names = [n["habit_name"] for n in context["habit_notifications"]]

        # Verification:
        # Index 0: open closes in 10m (can be completed now, closest deadline)
        # Index 1: open closes in 40m (can be completed now, later deadline)
        # Index 2: all day 5px (can be completed now anytime today)
        # Index 3: upcoming in 1h (opens next chronologically)
        # Index 4: upcoming in 3h (opens later chronologically)
        self.assertEqual(names[0], "open closes in 10m")
        self.assertEqual(names[1], "open closes in 40m")
        self.assertEqual(names[2], "all day 5px")
        self.assertEqual(names[3], "upcoming in 1h")
        self.assertEqual(names[4], "upcoming in 3h")

    def test_topbar_renders_bell_icon_and_dropdown(self):
        """Verify the bell button, badge, and notification panel render in the topbar HTML."""
        today = timezone.localdate()
        fake_now = timezone.make_aware(datetime.combine(today, time(9, 0, 0)))
        future_start = time(10, 0)
        future_end = time(11, 0)

        Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="drink water",
            frequency=Habit.Frequency.DAILY,
            start_date=today - timedelta(days=1),
            is_active=True,
            window_start_time=future_start,
            window_end_time=future_end,
            habit_type=Habit.HabitType.GENERAL,
        )

        self.client.force_login(self.user)
        session = self.client.session
        session["current_tenant_id"] = str(self.tenant.id)
        session.save()

        with patch("django.utils.timezone.localtime", return_value=fake_now):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        self.assertIn("topbar-controls-row", html)
        self.assertIn("habit-notifications-dropdown", html)
        self.assertIn("habitBellBtn", html)
        self.assertIn("habit-bell-badge", html)
        self.assertIn("habitNotificationMenu", html)
        self.assertIn("Your notifications", html)
        self.assertIn("drink water", html)
        self.assertIn("5 mins before", html)
        self.assertIn("goes off your wallet", html)
