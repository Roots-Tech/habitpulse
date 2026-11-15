import json
from datetime import time, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from tenants.models import Tenant, Membership
from habits.models import Habit, HabitCompletion, PushSubscription


class HabitAlarmAndReminderTests(TestCase):
    """
    Comprehensive test suite for the Habit Alarming & Intimation System:
    1. Habit model reminder fields & reminder_display property.
    2. API endpoints:
       - GET & POST /api/habits/<pk>/reminder/
       - POST /api/habits/<pk>/reminder/snooze/
       - GET /api/habits/reminders/active/
       - POST & DELETE /api/push/subscribe/
    3. Native phone calendar sync (.ics export with VALARM).
    4. Service worker push & notificationclick event handlers.
    5. Admin vs Regular user catalog button visibility.
    """

    def setUp(self):
        self.client = Client(SERVER_NAME="127.0.0.1")

        # Create workspace tenant
        self.tenant = Tenant.objects.create(name="Alarm Test Workspace", slug="alarm-ws")

        # Create regular user
        self.user = User.objects.create_user(
            username="regular_alex",
            email="alex@example.com",
            password="Password123!",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role="OWNER",
            status="ACTIVE",
        )

        # Create super admin
        self.admin_user = User.objects.create_superuser(
            username="admin_sarah",
            email="sarah@example.com",
            password="Password123!",
            role=User.Role.SUPER_ADMIN,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.admin_user,
            role="OWNER",
            status="ACTIVE",
        )

        # Create a test habit
        self.habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Morning Meditation",
            frequency=Habit.Frequency.DAILY,
            habit_type=Habit.HabitType.GENERAL,
            reminder_enabled=False,
            reminder_time=None,
        )

    def _login_user(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_tenant_id"] = self.tenant.id
        session.save()

    def test_habit_reminder_fields_and_display_property(self):
        """Verify reminder defaults and human-readable reminder_display."""
        self.assertFalse(self.habit.reminder_enabled)
        self.assertIsNone(self.habit.reminder_display)

        # Set standard alarm
        self.habit.reminder_enabled = True
        self.habit.reminder_time = time(8, 30)
        self.habit.reminder_snooze_interval = 0
        self.habit.save()
        self.assertEqual(self.habit.reminder_display, "8:30 AM")

        # Hourly snooze
        self.habit.reminder_snooze_interval = 60
        self.habit.save()
        self.assertEqual(self.habit.reminder_display, "8:30 AM (Hourly)")

        # 15m snooze
        self.habit.reminder_snooze_interval = 15
        self.habit.save()
        self.assertEqual(self.habit.reminder_display, "8:30 AM (15m snooze)")

    def test_habit_reminder_api_get_and_post(self):
        """Verify /api/habits/<pk>/reminder/ GET and POST functionality."""
        self._login_user(self.user)

        # GET initially
        get_res = self.client.get(reverse("api:habit_reminder", kwargs={"pk": self.habit.pk}))
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertEqual(data["habit_id"], self.habit.pk)
        self.assertFalse(data["reminder_enabled"])

        # POST to enable alarm at 07:15 with 60m snooze
        post_payload = {
            "reminder_enabled": True,
            "reminder_time": "07:15",
            "reminder_snooze_interval": 60,
        }
        post_res = self.client.post(
            reverse("api:habit_reminder", kwargs={"pk": self.habit.pk}),
            data=json.dumps(post_payload),
            content_type="application/json",
        )
        self.assertEqual(post_res.status_code, 200)
        post_data = post_res.json()
        self.assertTrue(post_data["success"])
        self.assertTrue(post_data["reminder_enabled"])
        self.assertEqual(post_data["reminder_time"], "07:15")
        self.assertIn("7:15 AM (Hourly)", post_data["reminder_display"])

        # Verify DB updated
        self.habit.refresh_from_db()
        self.assertTrue(self.habit.reminder_enabled)
        self.assertEqual(self.habit.reminder_time, time(7, 15))
        self.assertEqual(self.habit.reminder_snooze_interval, 60)

    def test_habit_reminder_api_forbidden_for_other_user(self):
        """Verify user cannot modify alarms of habits they do not own."""
        other_tenant = Tenant.objects.create(name="Other Workspace", slug="other-ws")
        other_user = User.objects.create_user(
            username="other_bob",
            email="bob@example.com",
            password="Password123!",
        )
        Membership.objects.create(tenant=other_tenant, user=other_user, role="OWNER", status="ACTIVE")

        self.client.force_login(other_user)
        session = self.client.session
        session["current_tenant_id"] = str(other_tenant.id)
        session.save()

        res = self.client.post(
            reverse("api:habit_reminder", kwargs={"pk": self.habit.pk}),
            data=json.dumps({"reminder_enabled": True, "reminder_time": "09:00"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_habit_reminder_snooze_api(self):
        """Verify /api/habits/<pk>/reminder/snooze/ updates snoozed_until."""
        self._login_user(self.user)

        res = self.client.post(
            reverse("api:habit_reminder_snooze", kwargs={"pk": self.habit.pk}),
            data=json.dumps({"minutes": 45}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["minutes"], 45)

        self.habit.refresh_from_db()
        self.assertIsNotNone(self.habit.snoozed_until)
        # Snooze should be roughly 45 minutes from now
        diff = (self.habit.snoozed_until - timezone.now()).total_seconds()
        self.assertGreater(diff, 40 * 60)
        self.assertLess(diff, 50 * 60)

    def test_active_reminders_api_suppresses_completed_habits(self):
        """Verify active alarms API excludes habits already marked done today."""
        self._login_user(self.user)
        self.habit.reminder_enabled = True
        self.habit.reminder_time = time(8, 0)
        self.habit.save()

        # Before completion: habit is in active alarms
        res = self.client.get(reverse("api:active_reminders"))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        active_ids = [r["id"] for r in data["reminders"]]
        self.assertIn(self.habit.pk, active_ids)

        # Mark habit completed for today
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=self.habit,
            completion_date=timezone.localdate(),
        )

        # After completion: habit is removed from active alarms
        res2 = self.client.get(reverse("api:active_reminders"))
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        active_ids2 = [r["id"] for r in data2["reminders"]]
        self.assertNotIn(self.habit.pk, active_ids2)

    def test_push_subscription_api(self):
        """Verify /api/push/subscribe/ POST and DELETE endpoints."""
        self._login_user(self.user)

        endpoint_url = "https://fcm.googleapis.com/fcm/send/test-sub-token-123"
        payload = {
            "endpoint": endpoint_url,
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9t0A4If_ZqV26PbVQGjJ2-87lzqy3rE",
                "auth": "tBHItJI5svbpez7KI4CCXg",
            }
        }

        # Subscribe
        sub_res = self.client.post(
            reverse("api:push_subscribe"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(sub_res.status_code, 200)
        self.assertTrue(sub_res.json()["success"])

        # Check in DB
        sub = PushSubscription.objects.filter(user=self.user, endpoint=endpoint_url).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.p256dh, payload["keys"]["p256dh"])

        # Unsubscribe
        del_res = self.client.delete(
            reverse("api:push_subscribe"),
            data=json.dumps({"endpoint": endpoint_url}),
            content_type="application/json",
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(PushSubscription.objects.filter(user=self.user, endpoint=endpoint_url).exists())

    def test_habit_calendar_ics_export(self):
        """Verify .ics export returns valid iCalendar data with VALARM."""
        self._login_user(self.user)
        self.habit.reminder_enabled = True
        self.habit.reminder_time = time(7, 30)
        self.habit.reminder_snooze_interval = 60
        self.habit.save()

        res = self.client.get(reverse("habit_calendar_ics", kwargs={"pk": self.habit.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn("attachment; filename=", res.headers["Content-Disposition"])

        content = res.content.decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("BEGIN:VALARM", content)
        self.assertIn("TRIGGER:-PT0M", content)
        self.assertIn("SUMMARY:⏰ HabitPulse: Morning Meditation", content)
        self.assertIn("RRULE:FREQ=DAILY", content)
        self.assertIn("DURATION:PT60M", content)
        self.assertIn("END:VCALENDAR", content)

    def test_service_worker_includes_push_and_notificationclick(self):
        """Verify sw.js serves push and notificationclick event listeners."""
        res = self.client.get(reverse("pwa_service_worker"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("addEventListener('push'", content)
        self.assertIn("addEventListener('notificationclick'", content)
        self.assertIn("showNotification", content)

    def test_catalog_buttons_strictly_hidden_from_regular_users(self):
        """
        Verify Download Catalog and Upload Catalog buttons are strictly hidden
        from regular users and only visible to Super Admins.
        """
        # Regular user view
        self._login_user(self.user)
        res_user = self.client.get(reverse("habit_list"))
        self.assertEqual(res_user.status_code, 200)
        content_user = res_user.content.decode("utf-8")
        self.assertNotIn("Download Catalog (JSON)", content_user)
        self.assertNotIn("Upload Catalog (JSON)", content_user)
        self.assertNotIn("catalog-import-modal", content_user)

        # Super Admin view
        self._login_user(self.admin_user)
        res_admin = self.client.get(reverse("habit_list"))
        self.assertEqual(res_admin.status_code, 200)
        content_admin = res_admin.content.decode("utf-8")
        self.assertIn("Download Catalog (JSON)", content_admin)
        self.assertIn("Upload Catalog (JSON)", content_admin)
        self.assertIn("catalog-import-modal", content_admin)

    def test_dashboard_renders_alarm_button_and_global_modal(self):
        """
        Verify the dashboard habit card renders the alert/bell button
        and the global alarm modal is accessible on the dashboard page.
        """
        self._login_user(self.user)
        self.habit.reminder_enabled = True
        self.habit.reminder_time = time(10, 0)
        self.habit.save()

        res = self.client.get(reverse("dashboard"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("habit-alarm-btn", content)
        self.assertIn("10:00 AM", content)
        self.assertIn("habit-alarm-modal", content)

    def test_test_push_api(self):
        """Verify /api/v1/habits/reminders/test-push/ sends test notification."""
        self._login_user(self.user)
        res = self.client.post(
            reverse("api:test_habit_reminder_push"),
            data=json.dumps({"habit_id": self.habit.pk}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("message", data)

    def test_dispatch_due_habit_alarms_scheduler(self):
        """Verify the background alarm dispatcher marks last_reminded_at."""
        from habits.alarm_scheduler import dispatch_due_habit_alarms

        self.habit.reminder_enabled = True
        # Set reminder time in the past for today so it's due
        now_time = timezone.localtime().time()
        past_time = time(max(0, now_time.hour - 1), 0)
        self.habit.reminder_time = past_time
        self.habit.last_reminded_at = None
        self.habit.save()

        dispatched = dispatch_due_habit_alarms()
        self.habit.refresh_from_db()
        self.assertIsNotNone(self.habit.last_reminded_at)
