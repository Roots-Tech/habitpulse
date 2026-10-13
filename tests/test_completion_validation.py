from datetime import time, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from habits.models import Habit, HabitCompletion
from habits.validators import (
    HabitCompletionValidationEngine,
    TimeWindowValidator,
    EvidenceFileValidator,
    NumericTargetValidator,
)
from tenants.models import Tenant
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class CompletionValidationEngineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="validator_user",
            email="validator@example.com",
            password="Password123!",
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "Validation Workspace")
        self.today = timezone.localdate()

    def test_time_window_validator_within_window(self):
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Morning Meditation",
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(6, 0),
            window_end_time=time(9, 30),
            start_date=self.today,
        )
        validator = TimeWindowValidator()
        mock_now = timezone.make_aware(timezone.datetime(2026, 10, 11, 7, 30, 0))
        result = validator.validate(habit, {}, {}, current_dt=mock_now)
        self.assertTrue(result.is_valid)

    def test_time_window_validator_outside_window(self):
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Early Run",
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(6, 0),
            window_end_time=time(9, 30),
            start_date=self.today,
        )
        validator = TimeWindowValidator()

        # Before window
        early_dt = timezone.make_aware(timezone.datetime(2026, 10, 11, 5, 45, 0))
        result_early = validator.validate(habit, {}, {}, current_dt=early_dt)
        self.assertFalse(result_early.is_valid)
        self.assertIn("Locked", result_early.error_message)

        # After window
        late_dt = timezone.make_aware(timezone.datetime(2026, 10, 11, 10, 15, 0))
        result_late = validator.validate(habit, {}, {}, current_dt=late_dt)
        self.assertFalse(result_late.is_valid)
        self.assertIn("Window closed", result_late.error_message)

    def test_evidence_file_validator(self):
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Gym Workout",
            validation_rule=Habit.ValidationRule.EVIDENCE_FILE,
            start_date=self.today,
        )
        validator = EvidenceFileValidator()

        # Missing file
        res_missing = validator.validate(habit, {}, {})
        self.assertFalse(res_missing.is_valid)
        self.assertIn("Proof of completion is required", res_missing.error_message)

        # Invalid extension
        bad_file = SimpleUploadedFile("malware.exe", b"malicious data", content_type="application/octet-stream")
        res_bad = validator.validate(habit, {}, {"evidence_file": bad_file})
        self.assertFalse(res_bad.is_valid)
        self.assertIn("Unsupported file format", res_bad.error_message)

        # Valid jpg file
        good_file = SimpleUploadedFile("workout.jpg", b"fake image bytes", content_type="image/jpeg")
        res_good = validator.validate(habit, {}, {"evidence_file": good_file})
        self.assertTrue(res_good.is_valid)

        # File too large (> 5MB)
        huge_file = SimpleUploadedFile("huge.png", b"x" * (6 * 1024 * 1024), content_type="image/png")
        res_large = validator.validate(habit, {}, {"evidence_file": huge_file})
        self.assertFalse(res_large.is_valid)
        self.assertIn("File is too large", res_large.error_message)

    def test_numeric_target_validator(self):
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Read Book",
            validation_rule=Habit.ValidationRule.NUMERIC_TARGET,
            target_value=Decimal("30.00"),
            unit_label="pages",
            start_date=self.today,
        )
        validator = NumericTargetValidator()

        # Missing value
        res_missing = validator.validate(habit, {}, {})
        self.assertFalse(res_missing.is_valid)

        # Invalid string
        res_invalid = validator.validate(habit, {"logged_value": "not-a-number"}, {})
        self.assertFalse(res_invalid.is_valid)

        # Below target (e.g. 20 < 30)
        res_under = validator.validate(habit, {"logged_value": "20"}, {})
        self.assertFalse(res_under.is_valid)
        self.assertIn("Goal not met", res_under.error_message)

        # Meets target (e.g. 30 == 30)
        res_met = validator.validate(habit, {"logged_value": "30"}, {})
        self.assertTrue(res_met.is_valid)

        # Exceeds target (e.g. 45 > 30)
        res_exceeded = validator.validate(habit, {"logged_value": "45.5"}, {})
        self.assertTrue(res_exceeded.is_valid)


class CompletionValidationViewsIntegrationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="view_user",
            email="views@example.com",
            password="Password123!",
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "Views Workspace")
        self.client.login(username="view_user", password="Password123!")

        session = self.client.session
        session["active_tenant_id"] = self.tenant.id
        session.save()

        self.today = timezone.localdate()

    def test_complete_habit_with_evidence_upload(self):
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Daily Running",
            validation_rule=Habit.ValidationRule.EVIDENCE_FILE,
            start_date=self.today,
        )

        url = reverse("habit_complete", kwargs={"pk": habit.pk})

        # Submit without file -> fails
        response = self.client.post(url, follow=True)
        self.assertEqual(HabitCompletion.objects.filter(habit=habit).count(), 0)

        # Submit with valid image proof
        proof = SimpleUploadedFile("run_track.png", b"image data content", content_type="image/png")
        response = self.client.post(url, {"evidence_file": proof, "notes": "5km in 28 mins"}, follow=True)
        self.assertEqual(response.status_code, 200)

        completion = HabitCompletion.objects.filter(habit=habit, completion_date=self.today).first()
        self.assertIsNotNone(completion)
        self.assertTrue(bool(completion.evidence_file))
        self.assertIn("tenants", completion.evidence_file.name)
        self.assertIn(self.tenant.slug, completion.evidence_file.name)
        self.assertEqual(completion.notes, "5km in 28 mins")

    def test_complete_habit_with_numeric_metric(self):
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Solve Problems",
            validation_rule=Habit.ValidationRule.NUMERIC_TARGET,
            target_value=Decimal("5"),
            unit_label="problems",
            start_date=self.today,
        )

        url = reverse("habit_complete", kwargs={"pk": habit.pk})

        # Submit below target (3 < 5)
        response = self.client.post(url, {"logged_value": "3"}, follow=True)
        self.assertEqual(HabitCompletion.objects.filter(habit=habit).count(), 0)

        # Submit meeting target (6 >= 5)
        response = self.client.post(url, {"logged_value": "6", "notes": "Hard DP questions"}, follow=True)
        self.assertEqual(response.status_code, 200)

        completion = HabitCompletion.objects.filter(habit=habit, completion_date=self.today).first()
        self.assertIsNotNone(completion)
        self.assertEqual(completion.logged_value, Decimal("6"))
        self.assertEqual(completion.notes, "Hard DP questions")

    def test_time_window_habit_blocks_completion_when_locked(self):
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Night Journaling",
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(21, 0),  # 9:00 PM
            window_end_time=time(23, 30),  # 11:30 PM
            start_date=self.today,
        )

        url = reverse("habit_complete", kwargs={"pk": habit.pk})

        # When current time is 2:00 PM (14:00)
        afternoon_dt = timezone.make_aware(
            timezone.datetime(self.today.year, self.today.month, self.today.day, 14, 0, 0)
        )
        with patch("django.utils.timezone.localtime", return_value=afternoon_dt):
            response = self.client.post(url, follow=True)
            self.assertEqual(HabitCompletion.objects.filter(habit=habit).count(), 0)

        # When current time is 9:45 PM (21:45)
        evening_dt = timezone.make_aware(
            timezone.datetime(self.today.year, self.today.month, self.today.day, 21, 45, 0)
        )
        with patch("django.utils.timezone.localtime", return_value=evening_dt):
            response = self.client.post(url, follow=True)
            self.assertEqual(HabitCompletion.objects.filter(habit=habit).count(), 1)
