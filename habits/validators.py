import os
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional
from django.utils import timezone

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

        # Validate file size
        if uploaded_file.size > MAX_EVIDENCE_FILE_SIZE_BYTES:
            max_mb = MAX_EVIDENCE_FILE_SIZE_BYTES / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                error_message=f"File is too large ({uploaded_file.size / (1024 * 1024):.1f} MB). Maximum size allowed is {max_mb:.0f} MB.",
                details={"field": "evidence_file", "reason": "file_too_large", "size": uploaded_file.size},
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


class HabitCompletionValidationEngine:
    """
    Validation engine orchestrating all completion checks for a habit.
    """
    def __init__(self):
        self.time_validator = TimeWindowValidator()
        self.evidence_validator = EvidenceFileValidator()
        self.numeric_validator = NumericTargetValidator()

    def get_validators_for_habit(self, habit) -> List[BaseCompletionValidator]:
        rule = habit.validation_rule
        validators = []
        if rule in [habit.ValidationRule.TIME_WINDOW, habit.ValidationRule.TIME_AND_EVIDENCE]:
            validators.append(self.time_validator)
        if rule in [habit.ValidationRule.EVIDENCE_FILE, habit.ValidationRule.TIME_AND_EVIDENCE]:
            validators.append(self.evidence_validator)
        if rule == habit.ValidationRule.NUMERIC_TARGET:
            validators.append(self.numeric_validator)
        return validators

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
