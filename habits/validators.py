import os
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional
from django.utils import timezone
from config.performance import profile_function

ALLOWED_EVIDENCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_EVIDENCE_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass
class ValidationResult:
    is_valid: bool
    error_message: str = ""
    details: Dict = field(default_factory=dict)


class BaseCompletionValidator:
    """Base interface for completion validation strategies."""
    def validate(self, habit, data: dict, files: dict, current_dt=None) -> ValidationResult:
        raise NotImplementedError


class TimeWindowValidator(BaseCompletionValidator):
    """
    Enforces that completion can only occur within habit.window_start_time and habit.window_end_time.
    Uses local workspace timezone.
    """
    def validate(self, habit, data: dict, files: dict, current_dt=None) -> ValidationResult:
        if not habit.has_time_window:
            return ValidationResult(is_valid=True)

        if not habit.window_start_time or not habit.window_end_time:
            return ValidationResult(is_valid=True)

        if current_dt is None:
            current_dt = timezone.localtime()
            current_time = current_dt.time()
        elif isinstance(current_dt, time):
            current_time = current_dt
        elif isinstance(current_dt, datetime):
            if timezone.is_aware(current_dt):
                current_dt = timezone.localtime(current_dt)
            current_time = current_dt.time()
        else:
            current_time = current_dt.time()

        start = habit.window_start_time
        end = habit.window_end_time

        effective_end = end
        if effective_end.second == 0 and effective_end.microsecond == 0:
            effective_end = effective_end.replace(second=59, microsecond=999999)

        if start <= current_time <= effective_end:
            return ValidationResult(is_valid=True)

        curr_fmt = current_time.strftime("%I:%M %p")
        start_fmt = start.strftime("%I:%M %p")
        end_fmt = end.strftime("%I:%M %p")

        if current_time < start:
            return ValidationResult(
                is_valid=False,
                error_message=f"Locked: This habit can only be completed between {start_fmt} and {end_fmt} (current time: {curr_fmt}).",
                details={"reason": "too_early", "current_time": curr_fmt, "window_start": start_fmt, "window_end": end_fmt},
            )
        else:
            return ValidationResult(
                is_valid=False,
                error_message=f"Window closed: This habit had to be completed between {start_fmt} and {end_fmt} (current time: {curr_fmt}).",
                details={"reason": "too_late", "current_time": curr_fmt, "window_start": start_fmt, "window_end": end_fmt},
            )


class EvidenceFileValidator(BaseCompletionValidator):
    """
    Ensures that an uploaded evidence file is provided, has a permitted extension,
    and does not exceed the maximum file size.
    """
    def validate(self, habit, data: dict, files: dict, current_dt=None) -> ValidationResult:
        if not habit.requires_evidence:
            return ValidationResult(is_valid=True)

        uploaded_file = files.get("evidence_file")
        if not uploaded_file:
            return ValidationResult(
                is_valid=False,
                error_message="Proof of completion is required. Please upload an image or document.",
                details={"field": "evidence_file", "reason": "missing_file"},
            )

        # Validate extension
        _, ext = os.path.splitext(uploaded_file.name)
        ext_lower = ext.lower()
        if ext_lower not in ALLOWED_EVIDENCE_EXTENSIONS:
            allowed_list = ", ".join(ALLOWED_EVIDENCE_EXTENSIONS).upper().replace(".", "")
            return ValidationResult(
                is_valid=False,
                error_message=f"Unsupported file format '{ext}'. Allowed formats: {allowed_list}.",
                details={"field": "evidence_file", "reason": "invalid_extension", "ext": ext},
            )

        # Validate file size first to immediately reject oversized payloads
        if uploaded_file.size > MAX_EVIDENCE_FILE_SIZE_BYTES:
            max_mb = MAX_EVIDENCE_FILE_SIZE_BYTES / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                error_message=f"File is too large ({uploaded_file.size / (1024 * 1024):.1f} MB). Maximum size allowed is {max_mb:.0f} MB.",
                details={"field": "evidence_file", "reason": "file_too_large", "size": uploaded_file.size},
            )

        # Validate magic bytes / file signatures to prevent disguised executables (SEC-04)
        try:
            initial_pos = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
            header = uploaded_file.read(16)
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(initial_pos)

            is_valid_header = False
            if ext_lower == ".pdf" and header.startswith(b"%PDF"):
                is_valid_header = True
            elif ext_lower == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
                is_valid_header = True
            elif ext_lower in (".jpg", ".jpeg") and header.startswith(b"\xff\xd8\xff"):
                is_valid_header = True
            elif ext_lower == ".webp" and header.startswith(b"RIFF") and b"WEBP" in header[:16]:
                is_valid_header = True

            if not is_valid_header:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Invalid or corrupted file content for '{uploaded_file.name}'. File does not match its declared format.",
                    details={"field": "evidence_file", "reason": "invalid_magic_bytes"},
                )
        except Exception:
            pass

        # AI Proof Relevance Verification
        if getattr(habit, "enable_ai_proof_verification", True):
            from .services import verify_proof_relevance
            ai_res = verify_proof_relevance(habit, uploaded_file)
            if not ai_res.get("is_valid", True):
                return ValidationResult(
                    is_valid=False,
                    error_message=f"AI Proof Verification Rejected: {ai_res.get('reason', 'Uploaded image does not appear relevant to this habit.')}",
                    details={"field": "evidence_file", "reason": "ai_rejected", "ai_details": ai_res},
                )

        return ValidationResult(is_valid=True)


class NumericTargetValidator(BaseCompletionValidator):
    """
    Ensures that numeric target habits receive a logged value that meets or exceeds the target.
    """
    def validate(self, habit, data: dict, files: dict, current_dt=None) -> ValidationResult:
        if not habit.requires_numeric:
            return ValidationResult(is_valid=True)

        raw_value = data.get("logged_value")
        if raw_value is None or str(raw_value).strip() == "":
            return ValidationResult(
                is_valid=False,
                error_message=f"A metric value is required (target: {habit.target_value} {habit.unit_label}).",
                details={"field": "logged_value", "reason": "missing_value"},
            )

        try:
            val = Decimal(str(raw_value).strip())
        except (InvalidOperation, ValueError, TypeError):
            return ValidationResult(
                is_valid=False,
                error_message="Please enter a valid numeric number.",
                details={"field": "logged_value", "reason": "invalid_number"},
            )

        if val <= Decimal("0"):
            return ValidationResult(
                is_valid=False,
                error_message="Logged value must be greater than zero.",
                details={"field": "logged_value", "reason": "zero_or_negative"},
            )

        if habit.target_value and val < habit.target_value:
            return ValidationResult(
                is_valid=False,
                error_message=f"Goal not met: You logged {val} {habit.unit_label}, but target is {habit.target_value} {habit.unit_label}.",
                details={"field": "logged_value", "reason": "target_unmet", "logged": str(val), "target": str(habit.target_value)},
            )

        return ValidationResult(is_valid=True)


import math

EARTH_RADIUS_METERS = 6371000.0


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes the great-circle distance between two geographic coordinates
    on Earth using the Haversine formula (returns distance in meters).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


class LocationValidator(BaseCompletionValidator):
    """
    Validates that user GPS coordinates are supplied and within the allowed radius
    of the habit's target location.
    """
    def validate(self, habit, data: dict, files: dict, current_dt=None) -> ValidationResult:
        if not getattr(habit, "is_location_restricted", False):
            return ValidationResult(is_valid=True)

        target_lat = getattr(habit, "target_latitude", None)
        target_lng = getattr(habit, "target_longitude", None)

        if target_lat is None or target_lng is None:
            return ValidationResult(is_valid=True)

        raw_lat = data.get("latitude")
        raw_lng = data.get("longitude")

        location_label = habit.location_name or "the designated location"

        if raw_lat is None or raw_lng is None or str(raw_lat).strip() == "" or str(raw_lng).strip() == "":
            return ValidationResult(
                is_valid=False,
                error_message=f"Location verification required: You must be present at '{location_label}' to mark this habit complete. Please enable GPS/location on your device.",
                details={"field": "location", "reason": "missing_coordinates"},
            )

        try:
            user_lat = float(str(raw_lat).strip())
            user_lng = float(str(raw_lng).strip())
        except (ValueError, TypeError):
            return ValidationResult(
                is_valid=False,
                error_message="Invalid GPS coordinates provided for location verification.",
                details={"field": "location", "reason": "invalid_coordinates"},
            )

        if not (-90.0 <= user_lat <= 90.0) or not (-180.0 <= user_lng <= 180.0):
            return ValidationResult(
                is_valid=False,
                error_message="GPS coordinates are out of valid range (-90 to +90 lat, -180 to +180 lng).",
                details={"field": "location", "reason": "coordinates_out_of_range"},
            )

        distance = haversine_distance_meters(
            user_lat,
            user_lng,
            float(target_lat),
            float(target_lng),
        )

        radius = habit.allowed_radius_meters or 150

        if distance > radius:
            distance_int = int(round(distance))
            if distance_int >= 1000:
                dist_str = f"{distance_int / 1000.0:.2f} km"
            else:
                dist_str = f"{distance_int} meters"

            return ValidationResult(
                is_valid=False,
                error_message=(
                    f"Location check failed: You are currently {dist_str} away from {location_label}. "
                    f"You must be within {radius} meters to complete this habit."
                ),
                details={
                    "field": "location",
                    "reason": "outside_radius",
                    "distance_meters": distance_int,
                    "allowed_radius_meters": radius,
                    "location_name": location_label,
                },
            )

        return ValidationResult(
            is_valid=True,
            details={
                "distance_meters": int(round(distance)),
                "latitude": user_lat,
                "longitude": user_lng,
            },
        )


class DurationValidator(BaseCompletionValidator):
    """
    Validates that the user has spent at least the minimum required duration
    on the habit session (in minutes).
    """
    def validate(self, habit, data: dict, files: dict, current_dt=None) -> ValidationResult:
        if not getattr(habit, "requires_duration", False):
            return ValidationResult(is_valid=True)

        min_required = habit.min_duration_minutes or 0
        raw_dur = data.get("duration_minutes") or data.get("logged_duration_minutes") or data.get("logged_duration")

        if raw_dur is None or str(raw_dur).strip() == "":
            return ValidationResult(
                is_valid=False,
                error_message=f"Session duration required: You must spend and log at least {min_required} minutes on this activity.",
                details={"field": "duration_minutes", "reason": "missing_duration", "required": min_required},
            )

        try:
            val = int(float(str(raw_dur).strip()))
        except (ValueError, TypeError):
            return ValidationResult(
                is_valid=False,
                error_message="Please enter a valid number of minutes for workout duration.",
                details={"field": "duration_minutes", "reason": "invalid_duration"},
            )

        if val < min_required:
            return ValidationResult(
                is_valid=False,
                error_message=f"Duration goal not met: You logged {val} minutes, but the requirement is at least {min_required} minutes.",
                details={"field": "duration_minutes", "reason": "duration_unmet", "logged": val, "required": min_required},
            )

        return ValidationResult(
            is_valid=True,
            details={"duration_minutes": val, "required_minutes": min_required},
        )


class HabitCompletionValidationEngine:
    """
    Validation engine orchestrating all completion checks for a habit.
    """
    def __init__(self):
        self.time_validator = TimeWindowValidator()
        self.evidence_validator = EvidenceFileValidator()
        self.numeric_validator = NumericTargetValidator()
        self.location_validator = LocationValidator()
        self.duration_validator = DurationValidator()

    def get_validators_for_habit(self, habit) -> List[BaseCompletionValidator]:
        validators = []
        if getattr(habit, "has_time_window", False):
            validators.append(self.time_validator)
        if getattr(habit, "is_location_restricted", False):
            validators.append(self.location_validator)
        if getattr(habit, "requires_duration", False):
            validators.append(self.duration_validator)
        if getattr(habit, "requires_numeric", False):
            validators.append(self.numeric_validator)
        if getattr(habit, "requires_evidence", False):
            validators.append(self.evidence_validator)
        return validators

    @profile_function("habits.validators.HabitCompletionValidationEngine.validate")
    def validate(self, habit, data: dict, files: dict, current_dt=None) -> List[str]:
        """
        Runs all active validators and returns list of error messages (empty if completely valid).
        """
        errors = []
        validators = self.get_validators_for_habit(habit)
        for validator in validators:
            result = validator.validate(habit, data, files, current_dt=current_dt)
            if not result.is_valid:
                errors.append(result.error_message)
        return errors
