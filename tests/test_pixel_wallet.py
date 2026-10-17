from datetime import date
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from tenants.models import Membership, Tenant
from habits.models import Habit, HabitCompletion, PixelWallet
from habits.services import calculate_user_pixel_wallet, get_pending_days_in_month


class PixelWalletTests(TestCase):
    """
    Tests for the dynamic Pixel Wallet gamification system:
    - Initial monthly allocation based on pending days in month
    - Formula verification for 1st of month (30 days -> 60 Px for 2 Px habit)
    - Formula verification for 18th of month (12 days -> 84 Px for 2 Px + 5 Px habits)
    - Daily loss deductions on missed days
    - Persistence in PixelWallet database model
    - UI views rendering (Profile/Workspace, General Settings, Dashboard)
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="shrinath_wallet",
            email="shrinath_wallet@example.com",
            password="Password123!",
        )
        self.tenant = Tenant.objects.create(
            name="Shrinath's Workspace",
            slug="shrinath-wallet-ws",
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role="OWNER",
            status="ACTIVE",
        )

    def test_pending_days_calculation(self):
        """
        Verify get_pending_days_in_month returns:
        - Exactly 30 pending days on day 1
        - Exactly 12 pending days on day 18
        """
        habit = Habit(
            name="Test Habit",
            start_date=date(2026, 10, 1),
            frequency=Habit.Frequency.DAILY,
        )
        # Day 1
        pending_day_1 = get_pending_days_in_month(habit, today=date(2026, 10, 1))
        self.assertEqual(pending_day_1, 30)

        # Day 18
        pending_day_18 = get_pending_days_in_month(habit, today=date(2026, 10, 18))
        self.assertEqual(pending_day_18, 12)

    def test_pixel_wallet_initial_allocation_day_18(self):
        """
        On the 18th with 2 habits (2 Px and 5 Px):
        - 12 pending days remaining in the month
        - Habit 1 (2 Px): 2 * 12 = 24 Px
        - Habit 2 (5 Px): 5 * 12 = 60 Px
        - Total allocated = 24 + 60 = 84 Px
        """
        # Habit 1: 2 Pixels (User created)
        h1 = Habit.objects.create(
            name="Eat 2 egg daily",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.GENERAL,
            pixel_score=2,
            start_date=date(2026, 10, 18),
            is_template=False,
        )

        # Habit 2: 5 Pixels (Predefined purpose)
        h2 = Habit.objects.create(
            name="Meditation 15 mins",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            pixel_score=5,
            start_date=date(2026, 10, 18),
            is_template=False,
        )

        today_18 = date(2026, 10, 18)
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant, today=today_18)

        self.assertEqual(wallet["pending_days"], 12)
        self.assertEqual(wallet["allocated_pixels"], 84)
        self.assertEqual(wallet["lost_pixels"], 0)
        self.assertEqual(wallet["current_balance"], 84)
        self.assertEqual(wallet["health_percent"], 100.0)

        # Breakdown checks
        self.assertEqual(len(wallet["habits_breakdown"]), 2)
        b1 = next(item for item in wallet["habits_breakdown"] if item["habit"].pk == h1.pk)
        b2 = next(item for item in wallet["habits_breakdown"] if item["habit"].pk == h2.pk)

        self.assertEqual(b1["allocated_pixels"], 24)
        self.assertEqual(b1["lost_pixels"], 0)
        self.assertEqual(b1["retained_pixels"], 24)

        self.assertEqual(b2["allocated_pixels"], 60)
        self.assertEqual(b2["lost_pixels"], 0)
        self.assertEqual(b2["retained_pixels"], 60)

        # Database record synchronization
        db_wallet = PixelWallet.objects.get(
            tenant=self.tenant,
            user=self.user,
            year=2026,
            month=10,
        )
        self.assertEqual(db_wallet.allocated_pixels, 84)
        self.assertEqual(db_wallet.lost_pixels, 0)
        self.assertEqual(db_wallet.current_balance, 84)

    def test_pixel_wallet_initial_allocation_day_1(self):
        """
        On the 1st of any month with a 2 Px habit:
        - 30 pending days
        - 2 * 30 = 60 Px allocated
        """
        Habit.objects.create(
            name="Morning Run",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.GENERAL,
            pixel_score=2,
            start_date=date(2026, 10, 1),
            is_template=False,
        )

        today_1 = date(2026, 10, 1)
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant, today=today_1)

        self.assertEqual(wallet["pending_days"], 30)
        self.assertEqual(wallet["allocated_pixels"], 60)
        self.assertEqual(wallet["current_balance"], 60)
        self.assertEqual(wallet["lost_pixels"], 0)
        self.assertEqual(wallet["health_percent"], 100.0)

    def test_pixel_wallet_daily_loss_on_missed_past_days(self):
        """
        Habit started on the 15th with 2 Px score.
        On the 18th (3 past days: 15th, 16th, 17th):
        - Day 15: Completed
        - Day 16: Missed -> 2 Px lost
        - Day 17: Missed -> 2 Px lost
        - Day 18: Today (pending, not counted as missed yet)
        Total loss = 4 Px.
        Allocated = 2 * 12 = 24 Px.
        Current Balance = 24 - 4 = 20 Px.
        """
        habit = Habit.objects.create(
            name="Evening Reading",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.GENERAL,
            pixel_score=2,
            start_date=date(2026, 10, 15),
            frequency=Habit.Frequency.DAILY,
            is_template=False,
        )

        # Mark only 2026-10-15 completed
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=habit,
            completion_date=date(2026, 10, 15),
        )

        today_18 = date(2026, 10, 18)
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant, today=today_18)

        self.assertEqual(wallet["allocated_pixels"], 24)
        self.assertEqual(wallet["lost_pixels"], 4)
        self.assertEqual(wallet["current_balance"], 20)
        self.assertEqual(wallet["health_percent"], round(20 / 24 * 100, 1))

        # Check DB record updated
        db_wallet = PixelWallet.objects.get(
            tenant=self.tenant,
            user=self.user,
            year=2026,
            month=10,
        )
        self.assertEqual(db_wallet.allocated_pixels, 24)
        self.assertEqual(db_wallet.lost_pixels, 4)
        self.assertEqual(db_wallet.current_balance, 20)

    def test_pixel_wallet_ui_renders_profile_settings_and_dashboard(self):
        """
        Integration test verifying that the Pixel Wallet renders properly across:
        1. Workspace / Profile page (/accounts/profile/)
        2. General Settings page (/accounts/settings/general/)
        3. Dashboard (/dashboard/)
        """
        today = timezone.localdate()
        Habit.objects.create(
            name="Eat 2 egg daily",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.GENERAL,
            pixel_score=2,
            start_date=today,
            is_template=False,
        )
        Habit.objects.create(
            name="Meditation 15 mins",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            pixel_score=5,
            start_date=today,
            is_template=False,
        )

        self.client.login(username="shrinath_wallet", password="Password123!")

        # 1. Profile / Workspace page
        profile_resp = self.client.get(reverse("profile"))
        self.assertEqual(profile_resp.status_code, 200)
        self.assertContains(profile_resp, "Main Pixel Wallet")
        self.assertContains(profile_resp, "Total Pixels: 7")
        self.assertContains(profile_resp, "Eat 2 egg daily")
        self.assertContains(profile_resp, "Meditation 15 mins")
        self.assertContains(profile_resp, "2 Pixels")
        self.assertContains(profile_resp, "5 Pixels")
        self.assertContains(profile_resp, "pixel_crown.png")

        # 2. General Settings page
        settings_resp = self.client.get(reverse("general_settings"))
        self.assertEqual(settings_resp.status_code, 200)
        self.assertContains(settings_resp, "Main Pixel Wallet")
        self.assertContains(settings_resp, "7")

        # 3. Dashboard page
        dash_resp = self.client.get(reverse("dashboard"))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, "Your Pixel Wallet")
        self.assertContains(dash_resp, "Wallet Energy")
        self.assertContains(dash_resp, "Total Pixels")
        self.assertContains(dash_resp, "View Wallet Details")
        self.assertContains(dash_resp, "wallet-breakdown-modal")
        self.assertContains(dash_resp, "settle")

        # 4. Profile direct tab navigation via ?tab=pixels
        profile_tab_resp = self.client.get(reverse("profile") + "?tab=pixels")
        self.assertEqual(profile_tab_resp.status_code, 200)
        self.assertContains(profile_tab_resp, 'id="tab-pixels"')
        self.assertContains(profile_tab_resp, "Main Pixel Wallet")

    def test_daily_pixel_outcome_and_risk_projection(self):
        """
        Verify live daily risk calculation and outcome projections:
        - 2 tasks scheduled today (2 Px and 5 Px = 7 Px total).
        - 0 completed: pending=7, projected balance if failed = current - 7.
        - 1 completed (5 Px): pending=2, message tells user they completed 5 out of 7, commit to earn remaining 2.
        - 2 completed: pending=0, 100% protected.
        """
        h1 = Habit.objects.create(
            name="Eat 2 egg daily",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.GENERAL,
            pixel_score=2,
            start_date=date(2026, 10, 18),
            is_template=False,
        )
        h2 = Habit.objects.create(
            name="Meditation 15 mins",
            tenant=self.tenant,
            created_by=self.user,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            pixel_score=5,
            start_date=date(2026, 10, 18),
            is_template=False,
        )

        today_18 = date(2026, 10, 18)

        # 1. Zero completed today
        w_none = calculate_user_pixel_wallet(self.user, tenant=self.tenant, today=today_18)
        self.assertEqual(w_none["today_scheduled_pixels"], 7)
        self.assertEqual(w_none["today_completed_pixels"], 0)
        self.assertEqual(w_none["today_pending_pixels"], 7)
        self.assertEqual(w_none["projected_balance_if_failed"], 84 - 7)
        self.assertIn("settle 7 pixels lower to 77", w_none["daily_outcome_text"])

        # 2. Complete Meditation 15 mins (5 Px)
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=h2,
            completion_date=today_18,
        )
        w_partial = calculate_user_pixel_wallet(self.user, tenant=self.tenant, today=today_18)
        self.assertEqual(w_partial["today_scheduled_pixels"], 7)
        self.assertEqual(w_partial["today_completed_pixels"], 5)
        self.assertEqual(w_partial["today_pending_pixels"], 2)
        self.assertEqual(w_partial["projected_balance_if_failed"], 84 - 2)
        self.assertIn("Out of total 7 pixels to achieve from the day you only did 5", w_partial["daily_outcome_text"])
        self.assertIn("commit yourself to earn the remaining 2", w_partial["daily_outcome_text"])

        # 3. Complete both (7 Px)
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=h1,
            completion_date=today_18,
        )
        w_all = calculate_user_pixel_wallet(self.user, tenant=self.tenant, today=today_18)
        self.assertEqual(w_all["today_scheduled_pixels"], 7)
        self.assertEqual(w_all["today_completed_pixels"], 7)
        self.assertEqual(w_all["today_pending_pixels"], 0)
        self.assertEqual(w_all["projected_balance_if_failed"], 84)
        self.assertIn("All 7 pixels secured for today", w_all["daily_outcome_text"])
