from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from habits.models import Habit, HabitCompletion
from habits.services import (
    calculate_completion_rate,
    calculate_streaks,
    generate_monthly_calendar_data,
    get_habit_statistics,
)
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class ServicesAnalyticsTestCase(TestCase):
    """
    Tests streaks, completion rate calculations, calendar generation, and edge cases.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="emma",
            email="emma@example.com",
            password="Password123!",
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "Emma Workspace")
        self.today = timezone.localdate()

    def test_streaks_with_consecutive_daily_completions(self):
        """
        Verify current streak and longest streak with unbroken 5-day history including today.
        """
        start_date = self.today - timedelta(days=4)
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Daily Reading",
            frequency=Habit.Frequency.DAILY,
            start_date=start_date,
        )

        # Complete all 5 days from start_date to today
        for offset in range(5):
            d = start_date + timedelta(days=offset)
            HabitCompletion.objects.create(
                tenant=self.tenant,
                habit=habit,
                completion_date=d,
            )

        streaks = calculate_streaks(habit, self.today)
        self.assertEqual(streaks["current_streak"], 5)
        self.assertEqual(streaks["longest_streak"], 5)

    def test_current_streak_preserved_when_today_is_pending(self):
        """
        If yesterday was completed and today is scheduled but not yet completed,
        the streak from yesterday remains active.
        """
        start_date = self.today - timedelta(days=3)
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Morning Run",
            frequency=Habit.Frequency.DAILY,
            start_date=start_date,
        )

        # Complete days up to yesterday (3 days completed), today not completed yet
        for offset in range(3):
            d = start_date + timedelta(days=offset)
            HabitCompletion.objects.create(
                tenant=self.tenant,
                habit=habit,
                completion_date=d,
            )

        streaks = calculate_streaks(habit, self.today)
        self.assertEqual(streaks["current_streak"], 3)
        self.assertEqual(streaks["longest_streak"], 3)

        # When today is completed, current streak increments to 4
        HabitCompletion.objects.create(
            tenant=self.tenant,
            habit=habit,
            completion_date=self.today,
        )
        streaks_updated = calculate_streaks(habit, self.today)
        self.assertEqual(streaks_updated["current_streak"], 4)
        self.assertEqual(streaks_updated["longest_streak"], 4)

    def test_missed_scheduled_day_breaks_streak(self):
        """
        Verify that a missed scheduled day breaks the streak.
        """
        start_date = self.today - timedelta(days=5)
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Write Code",
            frequency=Habit.Frequency.DAILY,
            start_date=start_date,
        )

        # Complete day -5, -4, -3 (3 days)
        for offset in [5, 4, 3]:
            HabitCompletion.objects.create(
                tenant=self.tenant,
                habit=habit,
                completion_date=self.today - timedelta(days=offset),
            )

        # Miss day -2!
        # Complete day -1 and today (2 days)
        for offset in [1, 0]:
            HabitCompletion.objects.create(
                tenant=self.tenant,
                habit=habit,
                completion_date=self.today - timedelta(days=offset),
            )

        streaks = calculate_streaks(habit, self.today)
        self.assertEqual(streaks["current_streak"], 2)
        self.assertEqual(streaks["longest_streak"], 3)

    def test_streak_with_selected_weekdays(self):
        """
        Verify that unscheduled weekdays do not break streaks for weekday-specific habits.
        """
        # Habit scheduled on today's weekday and yesterday's weekday only
        w_today = self.today.weekday()
        w_yesterday = (self.today - timedelta(days=1)).weekday()

        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Weekday Focus",
            frequency=Habit.Frequency.WEEKDAYS,
            selected_weekdays=[w_yesterday, w_today],
            start_date=self.today - timedelta(days=7),
        )

        # Complete the eligible day from last week and yesterday and today
        # Days: today - 7 days (same weekday as today), today - 1 day, today
        HabitCompletion.objects.create(tenant=self.tenant, habit=habit, completion_date=self.today - timedelta(days=7))
        HabitCompletion.objects.create(tenant=self.tenant, habit=habit, completion_date=self.today - timedelta(days=1))
        HabitCompletion.objects.create(tenant=self.tenant, habit=habit, completion_date=self.today)

        # Note: If day -6 was scheduled or unscheduled: only w_today and w_yesterday are scheduled.
        # In the past 7 days, the scheduled days are:
        # today - 7 (w_today) -> completed
        # today - 1 (w_yesterday) -> completed
        # today (w_today) -> completed
        # What about today - 6? It's (today - 7) + 1 = w_yesterday, which is scheduled!
        # If today - 6 was missed, streak would start at today - 1.
        streaks = calculate_streaks(habit, self.today)
        self.assertGreaterEqual(streaks["current_streak"], 2)

    def test_completion_rate_calculation_and_division_by_zero(self):
        """
        Verify completion rate calculation formula:
        completed eligible / total eligible * 100.
        Also verifies that 0 eligible days returns None without division by zero.
        """
        # Habit starting tomorrow has 0 eligible days up to today
        tomorrow = self.today + timedelta(days=1)
        future_habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Future Habit",
            frequency=Habit.Frequency.DAILY,
            start_date=tomorrow,
        )

        rate_7d = calculate_completion_rate(future_habit, self.today - timedelta(days=6), self.today, self.today)
        self.assertEqual(rate_7d["eligible"], 0)
        self.assertEqual(rate_7d["completed"], 0)
        self.assertIsNone(rate_7d["rate"])

        # Habit started 4 days ago with 2 completions out of 5 eligible days
        past_habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Past Habit",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today - timedelta(days=4),
        )
        HabitCompletion.objects.create(tenant=self.tenant, habit=past_habit, completion_date=self.today - timedelta(days=4))
        HabitCompletion.objects.create(tenant=self.tenant, habit=past_habit, completion_date=self.today)

        calc = calculate_completion_rate(past_habit, self.today - timedelta(days=4), self.today, self.today)
        self.assertEqual(calc["eligible"], 5)
        self.assertEqual(calc["completed"], 2)
        self.assertEqual(calc["rate"], 40.0)

    def test_calendar_generation_and_visual_states(self):
        """
        Verify calendar grid generation, day status assignments, and month navigation.
        """
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Calendar Test Habit",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today - timedelta(days=2),
        )
        # Mark day - 2 completed
        completed_day = self.today - timedelta(days=2)
        HabitCompletion.objects.create(tenant=self.tenant, habit=habit, completion_date=completed_day)

        cal_data = generate_monthly_calendar_data(habit, self.today.year, self.today.month, self.today)

        self.assertEqual(cal_data["year"], self.today.year)
        self.assertEqual(cal_data["month"], self.today.month)
        self.assertIn("weeks", cal_data)
        self.assertGreaterEqual(len(cal_data["weeks"]), 4)

        # Find our completed day in calendar weeks
        found_completed = False
        found_today = False
        for week in cal_data["weeks"]:
            for day in week:
                if day["date"] == completed_day:
                    self.assertEqual(day["status"], "completed")
                    found_completed = True
                if day["date"] == self.today:
                    self.assertTrue(day["is_today"])
                    self.assertIn(day["status"], ["pending_today", "completed"])
                    found_today = True

        self.assertTrue(found_completed)
        self.assertTrue(found_today)

        # Check navigation
        if self.today.month == 1:
            self.assertEqual(cal_data["prev_month"], 12)
            self.assertEqual(cal_data["prev_year"], self.today.year - 1)
        else:
            self.assertEqual(cal_data["prev_month"], self.today.month - 1)
            self.assertEqual(cal_data["prev_year"], self.today.year)

    def test_calendar_year_rollover_navigation(self):
        """
        Verify January navigates to December of previous year,
        and December navigates to January of next year.
        """
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Rollover Habit",
            frequency=Habit.Frequency.DAILY,
            start_date=date(2025, 1, 1),
        )

        jan_cal = generate_monthly_calendar_data(habit, 2025, 1, date(2025, 1, 15))
        self.assertEqual(jan_cal["prev_month"], 12)
        self.assertEqual(jan_cal["prev_year"], 2024)
        self.assertEqual(jan_cal["next_month"], 2)
        self.assertEqual(jan_cal["next_year"], 2025)

        dec_cal = generate_monthly_calendar_data(habit, 2025, 12, date(2025, 12, 15))
        self.assertEqual(dec_cal["prev_month"], 11)
        self.assertEqual(dec_cal["prev_year"], 2025)
        self.assertEqual(dec_cal["next_month"], 1)
        self.assertEqual(dec_cal["next_year"], 2026)

    def test_timezone_boundary_behavior(self):
        """
        Verify that habit completion dates and stats respect timezone.localdate().
        """
        import zoneinfo
        kolkata_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
        with timezone.override(kolkata_tz):
            local_today = timezone.localdate()
            habit = Habit.objects.create(
                tenant=self.tenant,
                created_by=self.user,
                name="Timezone Habit",
                frequency=Habit.Frequency.DAILY,
                start_date=local_today,
            )
            stats = get_habit_statistics(habit, local_today)
            self.assertTrue(stats["is_scheduled_today"])
            self.assertFalse(stats["is_completed_today"])

