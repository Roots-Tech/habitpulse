from datetime import date, timedelta
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from habits.models import Habit, HabitCompletion
from habits.validators import (
    HabitCompletionValidationEngine,
    LocationValidator,
    haversine_distance_meters,
)
from habits.forms import HabitForm, AdoptHabitPersonalizationForm
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


@pytest.fixture
def test_setup(db):
    user = User.objects.create_user(
        username="locationtester",
        email="location@test.com",
        password="TestPassword123!",
    )
    tenant, _ = create_personal_workspace_for_user(user, "Location Gym Workspace")
    client = Client()
    client.login(username="locationtester", password="TestPassword123!")
    return {
        "user": user,
        "tenant": tenant,
        "client": client,
    }


def test_haversine_distance_calculation():
    # Identical coordinates should yield 0 meters
    dist_zero = haversine_distance_meters(12.971598, 77.594566, 12.971598, 77.594566)
    assert round(dist_zero, 1) == 0.0

    # Distance between Bangalore Center and Indiranagar (~5.08 km)
    dist_known = haversine_distance_meters(12.971598, 77.594566, 12.978369, 77.640835)
    assert 5000 <= dist_known <= 5200


def test_location_validator_behavior(test_setup):
    tenant = test_setup["tenant"]
    user = test_setup["user"]

    # 1. Non-restricted habit passes validation even with no GPS data
    normal_habit = Habit.objects.create(
        tenant=tenant,
        created_by=user,
        name="Morning Stretches",
        is_location_restricted=False,
    )
    validator = LocationValidator()
    res_normal = validator.validate(normal_habit, {}, {})
    assert res_normal.is_valid is True

    # 2. Location-restricted gym habit: Target at Gold's Gym Indiranagar
    gym_lat = Decimal("12.978369")
    gym_lng = Decimal("77.640835")
    gym_habit = Habit.objects.create(
        tenant=tenant,
        created_by=user,
        name="Gym & Strength Training",
        is_location_restricted=True,
        location_name="Gold's Gym Indiranagar",
        target_latitude=gym_lat,
        target_longitude=gym_lng,
        allowed_radius_meters=150,
    )

    # Missing coordinates -> Fails
    res_missing = validator.validate(gym_habit, {}, {})
    assert res_missing.is_valid is False
    assert "Location verification required" in res_missing.error_message
    assert "Gold's Gym Indiranagar" in res_missing.error_message

    # Invalid coordinates -> Fails
    res_invalid = validator.validate(gym_habit, {"latitude": "invalid", "longitude": "coords"}, {})
    assert res_invalid.is_valid is False
    assert "Invalid GPS coordinates" in res_invalid.error_message

    # Coordinates out of globe range -> Fails
    res_out_of_range = validator.validate(gym_habit, {"latitude": "150.0", "longitude": "200.0"}, {})
    assert res_out_of_range.is_valid is False
    assert "out of valid range" in res_out_of_range.error_message

    # Within allowed radius (30 meters away) -> Passes
    near_lat = "12.978600"
    near_lng = "77.640835"
    res_near = validator.validate(gym_habit, {"latitude": near_lat, "longitude": near_lng}, {})
    assert res_near.is_valid is True
    assert res_near.details["distance_meters"] <= 150

    # Outside radius (2.5 km away) -> Fails with distance details
    far_lat = "12.960000"
    far_lng = "77.620000"
    res_far = validator.validate(gym_habit, {"latitude": far_lat, "longitude": far_lng}, {})
    assert res_far.is_valid is False
    assert "Location check failed" in res_far.error_message
    assert "Gold's Gym Indiranagar" in res_far.error_message
    assert res_far.details["distance_meters"] > 150


def test_engine_integrates_location_validator(test_setup):
    tenant = test_setup["tenant"]
    user = test_setup["user"]

    gym_habit = Habit.objects.create(
        tenant=tenant,
        created_by=user,
        name="Morning Gym",
        is_location_restricted=True,
        location_name="Downtown Fitness Club",
        target_latitude=Decimal("12.978369"),
        target_longitude=Decimal("77.640835"),
        allowed_radius_meters=100,
    )

    engine = HabitCompletionValidationEngine()

    # Validates and blocks when outside radius
    errors = engine.validate(gym_habit, {"latitude": "12.900000", "longitude": "77.600000"}, {})
    assert len(errors) == 1
    assert "Location check failed" in errors[0]

    # Validates and succeeds when inside radius
    errors_ok = engine.validate(gym_habit, {"latitude": "12.978370", "longitude": "77.640836"}, {})
    assert len(errors_ok) == 0


def test_habit_form_geofence_validation(test_setup):
    tenant = test_setup["tenant"]
    user = test_setup["user"]

    # When is_location_restricted=True, coordinates are required
    form_data = {
        "name": "Office Desk Meditation",
        "frequency": "DAILY",
        "start_date": timezone.localdate(),
        "is_active": True,
        "is_location_restricted": True,
        "location_name": "Main Office Building",
        # Missing latitude and longitude
    }
    form = HabitForm(data=form_data, tenant=tenant, user=user)
    assert not form.is_valid()
    assert "target_latitude" in form.errors
    assert "target_longitude" in form.errors

    # Valid coordinates and radius
    form_data_valid = {
        "name": "Office Desk Meditation",
        "frequency": "DAILY",
        "start_date": timezone.localdate(),
        "is_active": True,
        "is_location_restricted": True,
        "location_name": "Main Office Building",
        "target_latitude": "12.971598",
        "target_longitude": "77.594566",
        "allowed_radius_meters": 120,
    }
    form_valid = HabitForm(data=form_data_valid, tenant=tenant, user=user)
    assert form_valid.is_valid(), form_valid.errors
    habit = form_valid.save()
    assert habit.is_location_restricted is True
    assert habit.target_latitude == Decimal("12.971598")
    assert habit.allowed_radius_meters == 120


def test_habit_complete_view_geofenced_check_in(test_setup):
    tenant = test_setup["tenant"]
    user = test_setup["user"]
    client = test_setup["client"]

    gym_lat = Decimal("12.978369")
    gym_lng = Decimal("77.640835")
    habit = Habit.objects.create(
        tenant=tenant,
        created_by=user,
        name="Gold's Gym Session",
        is_location_restricted=True,
        location_name="Gold's Gym Indiranagar",
        target_latitude=gym_lat,
        target_longitude=gym_lng,
        allowed_radius_meters=150,
        start_date=timezone.localdate(),
    )

    complete_url = f"/habits/{habit.pk}/complete/"

    # 1. Attempt completion without coordinates -> Rejection
    resp_no_coords = client.post(complete_url, data={})
    assert resp_no_coords.status_code == 302
    assert not HabitCompletion.objects.filter(habit=habit).exists()

    # 2. Attempt completion with coordinates 3 km away -> Rejection
    resp_far = client.post(
        complete_url,
        data={
            "latitude": "12.950000",
            "longitude": "77.610000",
        },
    )
    assert resp_far.status_code == 302
    assert not HabitCompletion.objects.filter(habit=habit).exists()

    # 3. Attempt completion with coordinates at the gym (~15m away) -> Success!
    resp_success = client.post(
        complete_url,
        data={
            "latitude": "12.978400",
            "longitude": "77.640840",
            "notes": "Leg day finished!",
        },
    )
    assert resp_success.status_code == 302
    completion = HabitCompletion.objects.filter(habit=habit).first()
    assert completion is not None
    assert completion.notes == "Leg day finished!"
    assert completion.completion_latitude == Decimal("12.978400")
    assert completion.completion_longitude == Decimal("77.640840")
    assert completion.completion_distance_meters is not None
    assert completion.completion_distance_meters <= 150


def test_habit_complete_api_geofenced_check_in(test_setup):
    tenant = test_setup["tenant"]
    user = test_setup["user"]
    client = test_setup["client"]

    habit = Habit.objects.create(
        tenant=tenant,
        created_by=user,
        name="Climbing Gym Checkin",
        is_location_restricted=True,
        location_name="Boulders Hub",
        target_latitude=Decimal("12.970000"),
        target_longitude=Decimal("77.600000"),
        allowed_radius_meters=100,
        start_date=timezone.localdate(),
    )

    api_url = f"/api/v1/habits/{habit.pk}/complete/"

    # API call far away -> 400 error with message
    resp_fail = client.post(
        api_url,
        data={"latitude": "12.900000", "longitude": "77.500000"},
    )
    assert resp_fail.status_code == 400
    fail_data = resp_fail.json()
    assert fail_data["success"] is False
    assert "Location check failed" in fail_data["error"]

    # API call within radius -> 200 success
    resp_ok = client.post(
        api_url,
        data={"latitude": "12.970020", "longitude": "77.600020"},
    )
    assert resp_ok.status_code == 200
    ok_data = resp_ok.json()
    assert ok_data["success"] is True
    assert ok_data["is_completed_today"] is True


def test_adopt_template_with_location_personalization(test_setup):
    tenant = test_setup["tenant"]
    user = test_setup["user"]

    template = Habit.objects.create(
        tenant=None,
        created_by=user,
        name="Gym & Strength Training",
        habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
        is_template=True,
        frequency=Habit.Frequency.WEEKLY_TARGET,
        target_days_per_week=3,
        validation_rule=Habit.ValidationRule.STANDARD,
    )

    form_data = {
        "frequency": "WEEKLY_TARGET",
        "target_days_per_week": 4,
        "is_location_restricted": True,
        "location_name": "Gold's Gym Malleshwaram",
        "target_latitude": "13.003120",
        "target_longitude": "77.568450",
        "allowed_radius_meters": 200,
    }
    form = AdoptHabitPersonalizationForm(data=form_data, template_habit=template)
    assert form.is_valid(), form.errors
    cleaned = form.cleaned_data
    assert cleaned["is_location_restricted"] is True
    assert cleaned["target_latitude"] == Decimal("13.003120")
    assert cleaned["allowed_radius_meters"] == 200
