import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from tenants.models import Tenant


class Habit(models.Model):
    """
    Represents an individual habit with scheduling configuration.
    Strictly tenant-scoped.
    """
    class Category(models.TextChoices):
        HEALTH = "Health", "Health"
        FITNESS = "Fitness", "Fitness"
        LEARNING = "Learning", "Learning"
        PRODUCTIVITY = "Productivity", "Productivity"
        PERSONAL_DEV = "Personal Development", "Personal Development"
        OTHER = "Other", "Other"

    class Frequency(models.TextChoices):
        DAILY = "DAILY", "Every Day"
        WEEKDAYS = "WEEKDAYS", "Selected Days of the Week"

    class ValidationRule(models.TextChoices):
        STANDARD = "STANDARD", "Honor System (One-Click)"
        TIME_WINDOW = "TIME_WINDOW", "Time Window Constrained"
        EVIDENCE_FILE = "EVIDENCE_FILE", "Proof Required (Image/Doc)"
        NUMERIC_TARGET = "NUMERIC_TARGET", "Quantitative Goal"
        TIME_AND_EVIDENCE = "TIME_AND_EVIDENCE", "Time Window + Proof Required"

    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="habits",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_habits",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        blank=True,
        default=Category.OTHER,
    )
    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.DAILY,
    )
    # Stored as list of integers 0 (Monday) to 6 (Sunday)
    selected_weekdays = models.JSONField(
        default=list,
        blank=True,
        help_text="List of weekday indices (0=Mon, 6=Sun) when frequency is WEEKDAYS.",
    )
    start_date = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    # Validation Rule Configuration
    validation_rule = models.CharField(
        max_length=30,
        choices=ValidationRule.choices,
        default=ValidationRule.STANDARD,
        help_text="Verification requirement before a day can be marked complete.",
    )
    window_start_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Earliest time this habit can be completed (local workspace time).",
    )
    window_end_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Latest time this habit can be completed (local workspace time).",
    )
    target_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Target metric value to achieve (e.g., 30, 2.5, 10).",
    )
    unit_label = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Unit label (e.g. mins, km, pages, liters, reps).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "start_date"]),
        ]

    def clean(self):
        super().clean()
        errors = {}

        if self.frequency == self.Frequency.WEEKDAYS:
            if not self.selected_weekdays:
                errors["selected_weekdays"] = "Please select at least one day of the week for this frequency."
            else:
                for d in self.selected_weekdays:
                    if not isinstance(d, int) or d < 0 or d > 6:
                        errors["selected_weekdays"] = "Invalid weekday values."
                        break

        if self.validation_rule in [self.ValidationRule.TIME_WINDOW, self.ValidationRule.TIME_AND_EVIDENCE]:
            if not self.window_start_time:
                errors["window_start_time"] = "Window start time is required for this rule."
            if not self.window_end_time:
                errors["window_end_time"] = "Window end time is required for this rule."
            if self.window_start_time and self.window_end_time and self.window_start_time >= self.window_end_time:
                errors["window_end_time"] = "Window end time must be later than start time."

        if self.validation_rule == self.ValidationRule.NUMERIC_TARGET:
            if self.target_value is None or self.target_value <= 0:
                errors["target_value"] = "Target value must be greater than zero."
            if not self.unit_label or not self.unit_label.strip():
                errors["unit_label"] = "Unit label is required (e.g. pages, mins, km)."

        if errors:
            raise ValidationError(errors)

    @property
    def requires_modal(self):
        """
        True if completion requires user input (evidence file or numeric metric).
        """
        return self.validation_rule in [
            self.ValidationRule.EVIDENCE_FILE,
            self.ValidationRule.NUMERIC_TARGET,
            self.ValidationRule.TIME_AND_EVIDENCE,
        ]

    @property
    def requires_evidence(self):
        return self.validation_rule in [
            self.ValidationRule.EVIDENCE_FILE,
            self.ValidationRule.TIME_AND_EVIDENCE,
        ]

    @property
    def requires_numeric(self):
        return self.validation_rule == self.ValidationRule.NUMERIC_TARGET

    @property
    def has_time_window(self):
        return self.validation_rule in [
            self.ValidationRule.TIME_WINDOW,
            self.ValidationRule.TIME_AND_EVIDENCE,
        ]

    def get_time_window_display(self):
        """
        Formatted time window string, e.g. '06:00 AM - 09:30 AM'.
        """
        if self.has_time_window and self.window_start_time and self.window_end_time:
            return f"{self.window_start_time.strftime('%I:%M %p')} - {self.window_end_time.strftime('%I:%M %p')}"
        return ""

    def is_time_window_active(self, current_time=None):
        """
        Evaluates whether completion is allowed right now based on local time window.
        Returns tuple: (is_allowed: bool, status_message: str)
        """
        if not self.has_time_window or not self.window_start_time or not self.window_end_time:
            return (True, "Open")

        if current_time is None:
            current_time = timezone.localtime().time()

        if self.window_start_time <= current_time <= self.window_end_time:
            return (True, f"Open until {self.window_end_time.strftime('%I:%M %p')}")
        elif current_time < self.window_start_time:
            return (False, f"Locked until {self.window_start_time.strftime('%I:%M %p')}")
        else:
            return (False, f"Window closed at {self.window_end_time.strftime('%I:%M %p')}")

    def is_scheduled_for_date(self, target_date):
        """
        Determines if the habit is scheduled for target_date.
        Respects start_date and frequency configuration.
        """
        if target_date < self.start_date:
            return False
        if self.frequency == self.Frequency.DAILY:
            return True
        elif self.frequency == self.Frequency.WEEKDAYS:
            return target_date.weekday() in (self.selected_weekdays or [])
        return False

    def get_weekday_display_names(self):
        """
        Returns human-readable abbreviation of active weekdays.
        """
        if self.frequency == self.Frequency.DAILY:
            return "Daily"
        days_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        sorted_days = sorted(self.selected_weekdays or [])
        return ", ".join(days_map[d] for d in sorted_days) if sorted_days else "None"

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


def tenant_evidence_upload_path(instance, filename):
    """
    Stores evidence files in tenant-isolated directory:
    tenants/<tenant_slug>/evidence/habit_<habit_id>_<date>_<uuid>.<ext>
    """
    ext = filename.split(".")[-1].lower() if "." in filename else "bin"
    unique_id = uuid.uuid4().hex[:10]
    date_str = instance.completion_date.isoformat() if instance.completion_date else timezone.localdate().isoformat()
    slug = instance.tenant.slug if (instance.tenant_id and instance.tenant) else "tenant"
    return f"tenants/{slug}/evidence/habit_{instance.habit_id}_{date_str}_{unique_id}.{ext}"


class HabitCompletion(models.Model):
    """
    Records a habit completion for a specific calendar date.
    Enforces tenant match and database-level unique constraint on (habit, completion_date).
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    habit = models.ForeignKey(
        Habit,
        on_delete=models.CASCADE,
        related_name="completions",
    )
    completion_date = models.DateField()
    completed_at = models.DateTimeField(default=timezone.now, help_text="Timestamp when verification occurred.")
    evidence_file = models.FileField(
        upload_to=tenant_evidence_upload_path,
        null=True,
        blank=True,
        help_text="Uploaded evidence document or photo.",
    )
    logged_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual metric value logged by user.",
    )
    notes = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional submission note or reflection.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-completion_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["habit", "completion_date"],
                name="unique_habit_completion_date",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "completion_date"]),
            models.Index(fields=["habit", "completion_date"]),
        ]

    def clean(self):
        super().clean()
        if self.habit_id:
            # Multi-tenant invariant: Habit and HabitCompletion must belong to the same tenant
            if self.tenant_id and self.tenant_id != self.habit.tenant_id:
                raise ValidationError("Tenant mismatch: Completion tenant must match Habit tenant.")

            # Future date invariant
            today = timezone.localdate()
            if self.completion_date > today:
                raise ValidationError("Cannot mark habits as completed for future dates.")

            # Start date invariant
            if self.completion_date < self.habit.start_date:
                raise ValidationError("Cannot mark completions before the habit start date.")

            # Habit schedule invariant
            if not self.habit.is_scheduled_for_date(self.completion_date):
                raise ValidationError("Habit is not scheduled for this date.")

            # Evidence file required invariant
            if self.habit.requires_evidence and not self.evidence_file:
                raise ValidationError("Proof of completion (image or document) is required for this habit.")

            # Numeric target invariant
            if self.habit.requires_numeric:
                if self.logged_value is None:
                    raise ValidationError(f"A logged value is required (target: {self.habit.target_value} {self.habit.unit_label}).")
                if self.logged_value < self.habit.target_value:
                    raise ValidationError(f"Logged value {self.logged_value} is below the target of {self.habit.target_value} {self.habit.unit_label}.")

    def save(self, *args, **kwargs):
        if self.habit_id and not self.tenant_id:
            self.tenant = self.habit.tenant
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.habit.name} - {self.completion_date}"
