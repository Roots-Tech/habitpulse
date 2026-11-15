from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RolePermission
from habits.models import Habit, HabitCompletion, PixelRewardConfig
from habits.validators import (
    DurationValidator,
    HabitCompletionValidationEngine,
    LocationValidator,
    NumericTargetValidator,
    EvidenceFileValidator,
    TimeWindowValidator,
)
from habits.services import verify_proof_relevance
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class ModularValidationAndDynamicPixelsTestCase(TestCase):
    def setUp(self):
        RolePermission.get_for_role(User.Role.SUPER_ADMIN)
        RolePermission.get_for_role(User.Role.REGULAR_USER)

        # Create regular user & workspace
        self.user = User.objects.create_user(
            username="modular_user",
            email="modular@test.com",
            password="TestPassword123!",
            role=User.Role.REGULAR_USER,
        )
        self.tenant, _ = create_personal_workspace_for_user(self.user, "Modular Test Workspace")

        # Create admin user & workspace
        self.admin = User.objects.create_user(
            username="modular_admin",
            email="admin@test.com",
            password="AdminPassword123!",
            is_staff=True,
            is_superuser=True,
        )
        self.admin_tenant, _ = create_personal_workspace_for_user(self.admin, "Admin Catalog Space")

        # Client setup
        self.client = Client()
        self.client.login(username="modular_user", password="TestPassword123!")

        # Initialize PixelRewardConfig
        self.pixel_config, _ = PixelRewardConfig.objects.get_or_create(
            tenant=None,
            defaults={
                "user_defined_pixels": 2,
                "predefined_pixels": 5,
                "expert_prescribed_pixels": 10,
                "bonus_time_window": 2,
                "bonus_location": 3,
                "bonus_duration": 2,
                "bonus_numeric_target": 2,
                "bonus_evidence_proof": 3,
            },
        )
        self.pixel_config.user_defined_pixels = 2
        self.pixel_config.predefined_pixels = 5
        self.pixel_config.expert_prescribed_pixels = 10
        self.pixel_config.bonus_time_window = 2
        self.pixel_config.bonus_location = 3
        self.pixel_config.bonus_duration = 2
        self.pixel_config.bonus_numeric_target = 2
        self.pixel_config.bonus_evidence_proof = 3
        self.pixel_config.save()

    def test_dynamic_pixel_calculation_stacking(self):
        """
        Verify that habit pixel score is dynamically calculated by stacking
        base score with any combination of active verification bonuses.
        """
        config = self.pixel_config

        # 1. Base General Habit (No validations -> 2 Px)
        h_general = Habit(
            tenant=self.tenant,
            created_by=self.user,
            name="General Stretches",
            habit_type=Habit.HabitType.GENERAL,
        )
        assert config.calculate_habit_pixels(h_general) == 2

        # 2. General Habit with Time Window (+2) -> 4 Px
        h_general.enable_time_window = True
        h_general.window_start_time = time(6, 0)
        h_general.window_end_time = time(9, 0)
        assert config.calculate_habit_pixels(h_general) == 4

        # 3. Add Location Geofence (+3) -> 7 Px
        h_general.is_location_restricted = True
        h_general.target_latitude = Decimal("12.971598")
        h_general.target_longitude = Decimal("77.594566")
        assert config.calculate_habit_pixels(h_general) == 7

        # 4. Add Duration Tracking (+2) -> 9 Px
        h_general.enable_duration_requirement = True
        h_general.min_duration_minutes = 30
        assert config.calculate_habit_pixels(h_general) == 9

        # 5. Add Numeric Target (+2) -> 11 Px
        h_general.enable_numeric_target = True
        h_general.target_value = Decimal("5")
        h_general.unit_label = "km"
        assert config.calculate_habit_pixels(h_general) == 11

        # 6. Add Proof Upload (+3) -> 14 Px
        h_general.enable_evidence_upload = True
        assert config.calculate_habit_pixels(h_general) == 14

        # Save habit and verify pixel_score field is automatically synced on save
        h_general.save()
        h_general.refresh_from_db()
        assert h_general.pixel_score == 14

        # 7. Predefined Template with all 5 active -> 5 + (2 + 3 + 2 + 2 + 3) = 17 Px
        h_predefined = Habit(
            tenant=self.admin_tenant,
            created_by=self.admin,
            name="Gym Workout Pro",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            enable_time_window=True,
            window_start_time=time(6, 0),
            window_end_time=time(10, 0),
            is_location_restricted=True,
            target_latitude=Decimal("12.971598"),
            target_longitude=Decimal("77.594566"),
            enable_duration_requirement=True,
            min_duration_minutes=45,
            enable_numeric_target=True,
            target_value=Decimal("45"),
            unit_label="minutes",
            enable_evidence_upload=True,
        )
        assert config.calculate_habit_pixels(h_predefined) == 17

    def test_duration_validator(self):
        """
        Verify DurationValidator strictly enforces minimum minutes.
        """
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Evening Running",
            enable_duration_requirement=True,
            min_duration_minutes=30,
        )
        validator = DurationValidator()

        # Missing duration -> fails
        res_missing = validator.validate(habit, {}, {})
        assert res_missing.is_valid is False
        assert "must spend and log at least 30 minutes" in res_missing.error_message

        # Duration less than minimum -> fails
        res_short = validator.validate(habit, {"duration_minutes": "20"}, {})
        assert res_short.is_valid is False
        assert "at least 30 minutes" in res_short.error_message and "20 minutes" in res_short.error_message

        # Duration meeting or exceeding minimum -> passes
        res_exact = validator.validate(habit, {"duration_minutes": "30"}, {})
        assert res_exact.is_valid is True

        res_surpass = validator.validate(habit, {"duration_minutes": "45"}, {})
        assert res_surpass.is_valid is True

    def test_modular_multi_layer_validation_engine(self):
        """
        Test HabitCompletionValidationEngine when multiple verification layers
        are active simultaneously.
        """
        engine = HabitCompletionValidationEngine()

        # Create habit requiring Location (Bangalore) AND Duration (40m)
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Strict Gym Habit",
            is_location_restricted=True,
            target_latitude=Decimal("12.971598"),
            target_longitude=Decimal("77.594566"),
            allowed_radius_meters=150,
            enable_duration_requirement=True,
            min_duration_minutes=40,
        )

        # Case 1: Neither provided -> returns errors for both layers
        errors_empty = engine.validate(habit, {}, {})
        assert len(errors_empty) >= 2

        # Case 2: Location provided (at venue) but duration too short
        data_short_dur = {
            "latitude": "12.971598",
            "longitude": "77.594566",
            "duration_minutes": "25",
        }
        errors_short = engine.validate(habit, data_short_dur, {})
        assert len(errors_short) == 1
        assert "at least 40 minutes" in errors_short[0] and "25 minutes" in errors_short[0]

        # Case 3: Duration sufficient (45m) but location far away (~5km)
        data_far_loc = {
            "latitude": "12.978369",
            "longitude": "77.640835",
            "duration_minutes": "45",
        }
        errors_far = engine.validate(habit, data_far_loc, {})
        assert len(errors_far) == 1
        assert "away from the designated location" in errors_far[0]

        # Case 4: Both location and duration valid -> passes with zero errors
        data_valid = {
            "latitude": "12.971598",
            "longitude": "77.594566",
            "duration_minutes": "45",
        }
        errors_valid = engine.validate(habit, data_valid, {})
        assert len(errors_valid) == 0

    def test_ai_proof_relevance_service(self):
        """
        Verify AI proof relevance verification service with heuristic and mocked vision.
        """
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Gym Session",
            description="Daily weightlifting and cardio workout",
            enable_evidence_upload=True,
            enable_ai_proof_verification=True,
        )

        test_file = SimpleUploadedFile(
            name="workout.jpg",
            content=b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"x" * 1024,
            content_type="image/jpeg",
        )

        # 1. Fallback heuristic check (without API key)
        result_fallback = verify_proof_relevance(habit, test_file)
        assert result_fallback["status"] == "APPROVED"
        assert result_fallback["confidence"] is not None

        # 2. Mocked Gemini Vision API - Approved
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = mock_url.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"is_relevant\\": true, \\"confidence\\": 0.95, \\"reason\\": \\"Clear photo of gym barbells and workout gear\\"}"}]}}]}'

            with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_key"}):
                result_ai_approved = verify_proof_relevance(habit, test_file)
                assert result_ai_approved["status"] == "APPROVED"
                assert "gym barbells" in result_ai_approved["reason"].lower()

        # 3. Mocked Gemini Vision API - Rejected (e.g. food delivery receipt uploaded for gym)
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = mock_url.return_value.__enter__.return_value
            mock_resp.status = 200
            mock_resp.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"is_relevant\\": false, \\"confidence\\": 0.15, \\"reason\\": \\"Image is a grocery store receipt, unrelated to gym session\\"}"}]}}]}'

            with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy_key"}):
                result_ai_rejected = verify_proof_relevance(habit, test_file)
                assert result_ai_rejected["status"] == "REJECTED"
                assert "grocery store receipt" in result_ai_rejected["reason"].lower()

    def test_adopt_catalog_template_with_custom_modular_stack(self):
        """
        Verify that a regular user can adopt a catalog template and configure
        their personal modular verification requirements and get the stacked pixel rewards.
        """
        # Create catalog template linked to a 5 Px RuleStrategy
        from habits.models import RuleStrategy
        gym_strat = RuleStrategy.objects.create(
            name="Strength & Conditioning Standard",
            engine_type=RuleStrategy.EngineType.STANDARD,
            pixel_reward=5,
        )
        template = Habit.objects.create(
            tenant=self.admin_tenant,
            created_by=self.admin,
            name="Gym & Strength Training",
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            rule_strategy_ref=gym_strat,
            is_template=True,
        )

        adopt_url = reverse("habit_adopt", args=[template.pk])
        response = self.client.get(adopt_url)
        assert response.status_code == 200

        # User personalizes: adds Location Geofence (+3) and Duration Requirement (+2)
        post_data = {
            "frequency": "DAILY",
            "start_date": timezone.localdate().isoformat(),
            # Modular verifications
            "is_location_restricted": "on",
            "location_name": "Power Gym Indiranagar",
            "target_latitude": "12.971598",
            "target_longitude": "77.594566",
            "allowed_radius_meters": "150",
            "enable_duration_requirement": "on",
            "min_duration_minutes": "45",
        }

        adopt_post = self.client.post(adopt_url, data=post_data, follow=True)
        assert adopt_post.status_code == 200

        # Verify adopted habit exists in user's tenant
        adopted = Habit.objects.filter(tenant=self.tenant, template_source=template).first()
        assert adopted is not None
        assert adopted.is_location_restricted is True
        assert adopted.location_name == "Power Gym Indiranagar"
        assert adopted.requires_duration is True
        assert adopted.min_duration_minutes == 45
        # Dynamic pixels: Base 5 (predefined) + 3 (location) + 2 (duration) = 10 Px
        assert adopted.pixel_score == 10

        # Check badges list
        badges = adopted.get_active_verifications_list()
        badge_keys = [b["key"] for b in badges]
        assert "location" in badge_keys
        assert "duration" in badge_keys

    def test_web_and_api_completion_with_duration_logging(self):
        """
        Verify completion via API records duration, distance, and completion details.
        """
        today = timezone.localdate()
        habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Yoga Flow",
            is_location_restricted=True,
            target_latitude=Decimal("12.971598"),
            target_longitude=Decimal("77.594566"),
            allowed_radius_meters=200,
            enable_duration_requirement=True,
            min_duration_minutes=30,
            start_date=today,
        )

        # Complete via API with exact location and 35 minutes logged
        api_url = reverse("api:habit_complete", args=[habit.pk])
        payload = {
            "latitude": "12.971598",
            "longitude": "77.594566",
            "duration_minutes": "35",
            "notes": "Great morning session",
        }
        res = self.client.post(api_url, data=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True

        # Verify HabitCompletion record
        completion = HabitCompletion.objects.filter(habit=habit, completion_date=today).first()
        assert completion is not None
        assert completion.logged_duration_minutes == 35
        assert completion.completion_distance_meters == 0
        assert completion.notes == "Great morning session"
