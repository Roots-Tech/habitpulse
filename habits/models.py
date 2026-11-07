import uuid
from datetime import datetime, time
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from config.performance import profile_function
from tenants.models import Tenant


class HabitCategory(models.Model):
    """
    Master Data: Configurable Habit Categories with full CRUD support.
    Common system-wide master data managed by super admins and technical users,
    shared across all users and workspaces.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=20, blank=True, default="📁", help_text="Emoji or icon symbol")
    color = models.CharField(max_length=30, blank=True, default="#38bdf8", help_text="Badge color hex")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Habit Category"
        verbose_name_plural = "Habit Categories"

    def __str__(self):
        return self.name

    @property
    def habits_count(self):
        return self.habits.count()


class RuleStrategy(models.Model):
    """
    Master Data: Configurable Completion Validation Rule Strategies with full CRUD support.
    Common system-wide master data created and managed by the tech team, shared across all users and workspaces.
    """
    class EngineType(models.TextChoices):
        STANDARD = "STANDARD", "Honor System (One-Click)"
        TIME_WINDOW = "TIME_WINDOW", "Time Window Constrained"
        EVIDENCE_FILE = "EVIDENCE_FILE", "Proof Required (Image/Doc)"
        NUMERIC_TARGET = "NUMERIC_TARGET", "Quantitative Goal"
        TIME_AND_EVIDENCE = "TIME_AND_EVIDENCE", "Time Window + Proof Required"

    name = models.CharField(max_length=120, unique=True)
    engine_type = models.CharField(
        max_length=30,
        choices=EngineType.choices,
        default=EngineType.STANDARD,
        help_text="Underlying verification engine rule",
    )
    description = models.TextField(blank=True, default="", help_text="Explanation and instructions for this strategy")
    requires_evidence = models.BooleanField(default=False)
    requires_numeric = models.BooleanField(default=False)
    has_time_window = models.BooleanField(default=False)
    default_unit = models.CharField(max_length=30, blank=True, default="", help_text="Default metric unit (optional)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Rule Strategy"
        verbose_name_plural = "Rule Strategies"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-align requirement flags with selected engine_type
        if self.engine_type == self.EngineType.TIME_WINDOW:
            self.has_time_window = True
            self.requires_evidence = False
            self.requires_numeric = False
        elif self.engine_type == self.EngineType.EVIDENCE_FILE:
            self.requires_evidence = True
            self.has_time_window = False
            self.requires_numeric = False
        elif self.engine_type == self.EngineType.NUMERIC_TARGET:
            self.requires_numeric = True
            self.has_time_window = False
            self.requires_evidence = False
        elif self.engine_type == self.EngineType.TIME_AND_EVIDENCE:
            self.has_time_window = True
            self.requires_evidence = True
            self.requires_numeric = False
        elif self.engine_type == self.EngineType.STANDARD:
            self.has_time_window = False
            self.requires_evidence = False
            self.requires_numeric = False
        super().save(*args, **kwargs)

    @property
    def habits_count(self):
        return self.habits.count()

    @property
    def has_time_window_active(self):
        return bool(self.has_time_window or self.engine_type in [self.EngineType.TIME_WINDOW, self.EngineType.TIME_AND_EVIDENCE])

    @property
    def requires_numeric_active(self):
        return bool(self.requires_numeric or self.engine_type == self.EngineType.NUMERIC_TARGET)

    @property
    def requires_evidence_active(self):
        return bool(self.requires_evidence or self.engine_type in [self.EngineType.EVIDENCE_FILE, self.EngineType.TIME_AND_EVIDENCE])


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
        WEEKLY_TARGET = "WEEKLY_TARGET", "Days per Week (Flexible Weekly Target)"

    class ValidationRule(models.TextChoices):
        STANDARD = "STANDARD", "Honor System (One-Click)"
        TIME_WINDOW = "TIME_WINDOW", "Time Window Constrained"
        EVIDENCE_FILE = "EVIDENCE_FILE", "Proof Required (Image/Doc)"
        NUMERIC_TARGET = "NUMERIC_TARGET", "Quantitative Goal"
        TIME_AND_EVIDENCE = "TIME_AND_EVIDENCE", "Time Window + Proof Required"

    class HabitType(models.TextChoices):
        GENERAL = "GENERAL", "General Habit (Honor System)"
        PREDEFINED_PURPOSE = "PREDEFINED_PURPOSE", "Predefined Purposeful Habit"
        EXPERT_PRESCRIBED = "EXPERT_PRESCRIBED", "Expert Prescribed Habit"

    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    WEEKLY_TARGET_CHOICES = [
        (1, "1 Day / Week"),
        (2, "2 Days / Week"),
        (3, "3 Days / Week (Recommended for Gym Beginners / Full Body)"),
        (4, "4 Days / Week (Upper / Lower Split)"),
        (5, "5 Days / Week (Push / Pull / Legs Split)"),
        (6, "6 Days / Week (High Frequency / Advanced)"),
        (7, "7 Days / Week (Daily Target)"),
    ]

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="habits",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_habits",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    habit_type = models.CharField(
        max_length=30,
        choices=HabitType.choices,
        default=HabitType.GENERAL,
        help_text="Designation of habit type (General, Predefined Purposeful, or Expert Prescribed)",
    )
    is_template = models.BooleanField(
        default=False,
        help_text="Designates this habit as a catalog template available for any user to add.",
    )
    template_source = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adopted_habits",
        help_text="Reference to the catalog template this habit was adopted from.",
    )
    category_ref = models.ForeignKey(
        HabitCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="habits",
    )
    category = models.CharField(
        max_length=100,
        blank=True,
        default="Other",
    )
    rule_strategy_ref = models.ForeignKey(
        RuleStrategy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="habits",
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
    target_days_per_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Target frequency of days per week for weekly goal habits (e.g. Gym 3 days/week).",
    )
    purpose_patterns = models.JSONField(
        default=list,
        blank=True,
        help_text="List of regex keyword patterns to recognize intent for this template.",
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

    # Pixel Score Allocation
    pixel_score = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Pixel score allotted for completing this habit (2 for User-Created, 5 for Predefined, 10 for Expert).",
    )

    # Location Geofencing Configuration
    is_location_restricted = models.BooleanField(
        default=False,
        help_text="Require user to be physically present at target location to mark complete.",
    )
    location_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Venue name (e.g. Gold's Gym Indiranagar, Anytime Fitness, Central Park).",
    )
    target_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Target latitude coordinate (-90 to +90).",
    )
    target_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Target longitude coordinate (-180 to +180).",
    )
    allowed_radius_meters = models.PositiveIntegerField(
        default=150,
        help_text="Maximum allowed distance in meters from target location (e.g. 150m).",
    )

    # Modular Verification Layer Flags
    enable_time_window = models.BooleanField(
        default=False,
        help_text="Require completion within a specific daily time window.",
    )
    enable_numeric_target = models.BooleanField(
        default=False,
        help_text="Require logging a numerical progress metric reaching the target value.",
    )
    enable_evidence_upload = models.BooleanField(
        default=False,
        help_text="Require uploading proof of work (photo or document).",
    )
    enable_duration_requirement = models.BooleanField(
        default=False,
        help_text="Require minimum time spent on the activity (workout/session duration).",
    )
    min_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minimum session duration required in minutes.",
    )
    enable_ai_proof_verification = models.BooleanField(
        default=True,
        help_text="Automatically verify with AI vision whether uploaded proof genuinely matches habit purpose.",
    )
    idempotency_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        help_text="Unique client submission key to ensure idempotent creation.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "start_date"]),
            models.Index(fields=["is_template", "habit_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                name="unique_habit_idempotency_key",
                condition=models.Q(idempotency_key__isnull=False) & ~models.Q(idempotency_key=""),
            ),
            models.UniqueConstraint(
                fields=["tenant", "template_source"],
                name="unique_active_template_adoption_per_tenant",
                condition=models.Q(is_active=True, template_source__isnull=False),
            ),
        ]

    @property
    def is_general(self):
        return self.habit_type == self.HabitType.GENERAL

    @property
    def is_predefined_purpose(self):
        return self.habit_type == self.HabitType.PREDEFINED_PURPOSE

    @property
    def is_expert_prescribed(self):
        return self.habit_type == self.HabitType.EXPERT_PRESCRIBED

    def get_habit_type_badge(self):
        if self.habit_type == self.HabitType.PREDEFINED_PURPOSE:
            return {
                "label": "Predefined Purposeful",
                "class": "badge-purposeful",
                "icon": "🎯",
                "color": "#38bdf8",
                "bg": "rgba(56, 189, 248, 0.15)",
                "border": "rgba(56, 189, 248, 0.4)",
            }
        elif self.habit_type == self.HabitType.EXPERT_PRESCRIBED:
            return {
                "label": "Expert Prescribed",
                "class": "badge-expert",
                "icon": "🩺",
                "color": "#c084fc",
                "bg": "rgba(168, 85, 247, 0.15)",
                "border": "rgba(168, 85, 247, 0.4)",
            }
        return {
            "label": "General (Honor System)",
            "class": "badge-general",
            "icon": "👤",
            "color": "#34d399",
            "bg": "rgba(16, 185, 129, 0.15)",
            "border": "rgba(16, 185, 129, 0.4)",
        }

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

        if self.has_time_window:
            if not self.window_start_time:
                errors["window_start_time"] = "Window start time is required for this rule."
            if not self.window_end_time:
                errors["window_end_time"] = "Window end time is required for this rule."
            if self.window_start_time and self.window_end_time and self.window_start_time >= self.window_end_time:
                errors["window_end_time"] = "Window end time must be later than start time."

        if self.requires_numeric:
            if self.target_value is None or self.target_value <= 0:
                errors["target_value"] = "Target value must be greater than zero."
            if not self.unit_label or not self.unit_label.strip():
                errors["unit_label"] = "Unit label is required (e.g. pages, mins, km)."

        # Duration verification validation
        if self.enable_duration_requirement:
            if not self.min_duration_minutes or self.min_duration_minutes <= 0:
                errors["min_duration_minutes"] = "Minimum duration in minutes must be greater than zero."
            elif self.min_duration_minutes > 1440:
                errors["min_duration_minutes"] = "Minimum duration cannot exceed 24 hours (1440 minutes)."

        # Location Geofencing Validation
        if self.is_location_restricted:
            if self.target_latitude is not None and (self.target_latitude < -90 or self.target_latitude > 90):
                errors["target_latitude"] = "Target latitude must be between -90 and +90 degrees."
            if self.target_longitude is not None and (self.target_longitude < -180 or self.target_longitude > 180):
                errors["target_longitude"] = "Target longitude must be between -180 and +180 degrees."
            if self.allowed_radius_meters is not None and self.allowed_radius_meters < 10:
                errors["allowed_radius_meters"] = "Allowed radius must be at least 10 meters."

        # Pixel Score Rules Validation via Admin Configuration
        config = PixelRewardConfig.get_config(self.tenant)
        if self.habit_type == self.HabitType.GENERAL:
            if self.pixel_score is not None and self.pixel_score != config.user_defined_pixels:
                errors["pixel_score"] = f"User-created personal habits have an allotted pixel score of {config.user_defined_pixels}."
        else:
            if self.pixel_score is not None and self.pixel_score < 1:
                errors["pixel_score"] = "Pixel score must be at least 1."

        # Purpose-oriented duplicate restriction
        if not self.is_template and not self.template_source_id and self.name:
            is_new = (self.pk is None)
            name_changed = False
            if self.pk:
                orig = Habit.objects.filter(pk=self.pk).values("name").first()
                if orig and orig["name"].strip().lower() != self.name.strip().lower():
                    name_changed = True
            if is_new or name_changed:
                from .services import find_matching_predefined_template
                matched_template = find_matching_predefined_template(self.name, self.description)
                if matched_template and matched_template.pk != self.pk:
                    errors["name"] = (
                        f"A standardized predefined habit for this purpose already exists in the library: '{matched_template.name}'. "
                        f"User-defined custom habits for this purpose are restricted to eliminate redundant database records and maintain system performance. "
                        f"Please adopt '{matched_template.name}' from the Predefined Catalog to configure your personal schedule."
                    )

        if errors:
            raise ValidationError(errors)

    @property
    def is_weekly_target(self):
        return self.frequency == self.Frequency.WEEKLY_TARGET

    @property
    def effective_weekly_target(self):
        return self.target_days_per_week or 3

    @property
    def monthly_target_days(self):
        """Standard monthly target: weekly target * 4 weeks."""
        return self.effective_weekly_target * 4

    @property
    def has_time_window(self):
        return bool(self.enable_time_window or (self.validation_rule in [
            self.ValidationRule.TIME_WINDOW,
            self.ValidationRule.TIME_AND_EVIDENCE,
        ]))

    @property
    def requires_evidence(self):
        return bool(self.enable_evidence_upload or (self.validation_rule in [
            self.ValidationRule.EVIDENCE_FILE,
            self.ValidationRule.TIME_AND_EVIDENCE,
        ]))

    @property
    def requires_numeric(self):
        return bool(self.enable_numeric_target or (self.validation_rule == self.ValidationRule.NUMERIC_TARGET))

    @property
    def requires_duration(self):
        return bool(self.enable_duration_requirement and self.min_duration_minutes and self.min_duration_minutes > 0)

    @property
    def requires_modal(self):
        """
        True if completion requires user input (evidence file, numeric metric, duration, or geofence).
        """
        return bool(self.requires_evidence or self.requires_numeric or self.requires_duration or self.is_location_restricted)

    def get_active_verifications_list(self):
        """Returns human-readable badges for all active verification layers."""
        badges = []
        if self.has_time_window:
            badges.append({"key": "time", "icon": "⏰", "label": self.get_time_window_display() or "Time Window"})
        if self.is_location_restricted:
            loc = self.location_name or "Geofence"
            badges.append({"key": "location", "icon": "📍", "label": f"{loc} ({self.allowed_radius_meters}m)"})
        if self.requires_duration:
            badges.append({"key": "duration", "icon": "⏱️", "label": f"Min {self.min_duration_minutes}m"})
        if self.requires_numeric:
            badges.append({"key": "numeric", "icon": "🎯", "label": f"{self.target_value} {self.unit_label}"})
        if self.requires_evidence:
            ai_lbl = "AI Proof" if self.enable_ai_proof_verification else "Proof Upload"
            badges.append({"key": "evidence", "icon": "📎", "label": ai_lbl})
        if not badges:
            badges.append({"key": "honor", "icon": "🤝", "label": "Honor System"})
        return badges

    def get_time_window_display(self):
        """
        Formatted time window string, e.g. '06:00 AM - 09:30 AM'.
        """
        if self.has_time_window and self.window_start_time and self.window_end_time:
            return f"{self.window_start_time.strftime('%I:%M %p')} - {self.window_end_time.strftime('%I:%M %p')}"
        return ""

    @profile_function("habits.models.Habit.is_time_window_active")
    def is_time_window_active(self, current_time=None):
        """
        Evaluates whether completion is allowed right now based on local time window.
        Returns tuple: (is_allowed: bool, status_message: str)
        """
        if not self.has_time_window or not self.window_start_time or not self.window_end_time:
            return (True, "Open")

        if current_time is None:
            current_time = timezone.localtime().time()
        elif isinstance(current_time, datetime):
            if timezone.is_aware(current_time):
                current_time = timezone.localtime(current_time).time()
            else:
                current_time = current_time.time()

        effective_end = self.window_end_time
        if effective_end.second == 0 and effective_end.microsecond == 0:
            effective_end = effective_end.replace(second=59, microsecond=999999)

        if self.window_start_time <= current_time <= effective_end:
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
        elif self.frequency == self.Frequency.WEEKLY_TARGET:
            return True
        return False

    def get_weekday_display_names(self):
        """
        Returns human-readable abbreviation of active weekdays or weekly target.
        """
        if self.frequency == self.Frequency.WEEKLY_TARGET or self.target_days_per_week:
            return f"{self.effective_weekly_target} Days / Week"
        if self.frequency == self.Frequency.DAILY:
            return "Daily"
        days_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
        sorted_days = sorted(self.selected_weekdays or [])
        return ", ".join(days_map[d] for d in sorted_days) if sorted_days else "None"

    def get_frequency_display_custom(self):
        if self.frequency == self.Frequency.WEEKLY_TARGET or self.target_days_per_week:
            return f"{self.effective_weekly_target} Days / Week"
        return self.get_frequency_display()

    def save(self, *args, **kwargs):
        # 1. Synchronize category and category_ref
        if self.category:
            if not self.category_ref or self.category_ref.name != self.category:
                cat, _ = HabitCategory.objects.get_or_create(
                    name=self.category,
                    defaults={"is_active": True},
                )
                self.category_ref = cat
        elif self.category_ref:
            self.category = self.category_ref.name

        # 2. Synchronize validation_rule and rule_strategy_ref
        if self.validation_rule:
            if not self.rule_strategy_ref or self.rule_strategy_ref.engine_type != self.validation_rule:
                strat = RuleStrategy.objects.filter(
                    engine_type=self.validation_rule,
                ).first()
                if not strat:
                    label = dict(self.ValidationRule.choices).get(self.validation_rule, self.validation_rule)
                    strat, _ = RuleStrategy.objects.get_or_create(
                        name=label,
                        defaults={
                            "engine_type": self.validation_rule,
                            "is_active": True,
                        },
                    )
                self.rule_strategy_ref = strat
        elif self.rule_strategy_ref:
            self.validation_rule = self.rule_strategy_ref.engine_type

        # 3. Enforce dynamic stackable pixel score rules via Admin Configuration
        config = PixelRewardConfig.get_config(self.tenant)
        bonuses = config.calculate_bonuses(self)

        if self.habit_type == self.HabitType.GENERAL:
            self.pixel_score = config.user_defined_pixels + bonuses
        elif self.is_template:
            if not self.pixel_score or self.pixel_score < 1:
                self.pixel_score = config.get_pixel_for_type(self.habit_type) + bonuses
        elif self.template_source:
            template_base = self.template_source.pixel_score or config.get_pixel_for_type(self.habit_type)
            template_bonuses = config.calculate_bonuses(self.template_source)
            extra_bonuses = max(0, bonuses - template_bonuses) if bonuses >= template_bonuses else bonuses
            # If user added verification layers beyond the template, stack them on top of template base
            self.pixel_score = template_base + (extra_bonuses if bonuses > 0 and bonuses != extra_bonuses else bonuses)
        else:
            if not self.pixel_score or self.pixel_score < 1:
                self.pixel_score = config.get_pixel_for_type(self.habit_type) + bonuses
            elif bonuses > 0:
                self.pixel_score = self.pixel_score + bonuses

        super().save(*args, **kwargs)

    @property
    def pixel_badge(self):
        return {
            "score": self.pixel_score,
            "label": f"{self.pixel_score} Px",
            "full_label": f"{self.pixel_score} Pixels",
        }

    def __str__(self):
        tenant_name = self.tenant.name if self.tenant else "Catalog Template"
        return f"{self.name} ({tenant_name})"


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
    completion_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="User latitude coordinate at completion.",
    )
    completion_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="User longitude coordinate at completion.",
    )
    completion_distance_meters = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Calculated distance in meters from target location at completion.",
    )
    logged_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Actual duration spent in minutes.",
    )
    session_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when active habit session began.",
    )
    ai_verification_status = models.CharField(
        max_length=30,
        default="SKIPPED",
        choices=[
            ("APPROVED", "AI Approved"),
            ("REJECTED", "AI Rejected"),
            ("PENDING", "Pending Review"),
            ("SKIPPED", "Skipped / Offline"),
        ],
        help_text="Result of AI verification check on uploaded proof.",
    )
    ai_verification_reason = models.TextField(
        blank=True,
        default="",
        help_text="Detailed AI reasoning regarding evidence relevance.",
    )
    ai_confidence_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Confidence level (0.0 to 1.0) of AI proof verification.",
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


class PixelWallet(models.Model):
    """
    Main Pixel Wallet for a user within a workspace/tenant.
    Tracks monthly allocated pixels, deductions from missed habits,
    and current energized wallet balance.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="pixel_wallets",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pixel_wallets",
    )
    year = models.PositiveIntegerField(default=2026)
    month = models.PositiveIntegerField(default=10)
    allocated_pixels = models.PositiveIntegerField(
        default=0,
        help_text="Total pixels credited for the month based on daily scores * pending days",
    )
    lost_pixels = models.PositiveIntegerField(
        default=0,
        help_text="Pixels deducted due to missed habit days",
    )
    current_balance = models.PositiveIntegerField(
        default=0,
        help_text="Remaining energized pixels (allocated - lost)",
    )
    bonus_pixels = models.PositiveIntegerField(
        default=0,
        help_text="Additional bonus pixels allocated by Super Admin",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "-month"]
        unique_together = [("tenant", "user", "year", "month")]
        indexes = [
            models.Index(fields=["tenant", "user", "year", "month"]),
        ]

    def __str__(self):
        return f"Wallet for {self.user.username} ({self.month}/{self.year}): {self.current_balance} Px"

    @property
    def health_percent(self):
        if self.allocated_pixels <= 0:
            return 100.0
        return round((self.current_balance / self.allocated_pixels) * 100, 1)


class PixelAllocation(models.Model):
    """
    Audit record of additional pixel grants awarded by Super Admin to users or user groups.
    """
    class TargetType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual User"
        SELECTED = "SELECTED", "Selected Users"
        GROUP_REGULAR = "GROUP_REGULAR", "Regular Users"
        GROUP_TECHNICAL = "GROUP_TECHNICAL", "Technical Users"
        GROUP_SUPER = "GROUP_SUPER", "Super Admins"
        GROUP_ALL = "GROUP_ALL", "All Users"

    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="granted_pixel_allocations",
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_pixel_allocations",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="pixel_allocations",
    )
    amount = models.PositiveIntegerField(
        help_text="Number of additional pixels allocated",
    )
    target_type = models.CharField(
        max_length=30,
        choices=TargetType.choices,
        default=TargetType.INDIVIDUAL,
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Reason or note for this allocation",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount} Px to {self.recipient_user.username} by {self.admin_user.username} ({self.created_at:%Y-%m-%d})"



class PixelRequest(models.Model):
    """
    Tracks a user's request to redeem/withdraw pixels from their active wallet.
    Enforces balance limits, immediate wallet hold, and complete admin review
    with full settlement transaction tracking (wallet at request, requested, approved,
    refunded, and final settled balance).
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        APPROVED = "APPROVED", "Approved"
        PARTIALLY_APPROVED = "PARTIALLY_APPROVED", "Partially Approved"
        DECLINED = "DECLINED", "Declined"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="pixel_requests",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pixel_requests",
    )
    wallet_balance_at_request = models.PositiveIntegerField(
        help_text="User's wallet balance at the time the request was raised",
    )
    requested_amount = models.PositiveIntegerField(
        help_text="Number of pixels requested for redemption",
    )
    held_balance = models.PositiveIntegerField(
        default=0,
        help_text="Amount currently held from wallet while pending",
    )
    approved_amount = models.PositiveIntegerField(
        default=0,
        help_text="Number of pixels approved by admin upon review",
    )
    refunded_amount = models.PositiveIntegerField(
        default=0,
        help_text="Pixels returned to wallet if declined or partially approved",
    )
    final_balance_after_settlement = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Snapshot of user's wallet balance after review is finalized",
    )
    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    user_notes = models.TextField(
        blank=True,
        default="",
        help_text="User's explanation or purpose for the request",
    )
    admin_notes = models.TextField(
        blank=True,
        default="",
        help_text="Admin review feedback or reason for partial/declined decision",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_pixel_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "user", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"Request #{self.pk} by {self.user.username}: {self.requested_amount} Px ({self.status})"

    def get_status_badge(self):
        if self.status == self.Status.PENDING:
            return {
                "label": "Pending Review",
                "color": "#f59e0b",
                "bg": "rgba(245, 158, 11, 0.15)",
                "border": "rgba(245, 158, 11, 0.4)",
                "icon": "⏳"
            }
        elif self.status == self.Status.APPROVED:
            return {
                "label": "Approved",
                "color": "#10b981",
                "bg": "rgba(16, 185, 129, 0.15)",
                "border": "rgba(16, 185, 129, 0.4)",
                "icon": "✓"
            }
        elif self.status == self.Status.PARTIALLY_APPROVED:
            return {
                "label": "Partially Approved",
                "color": "#38bdf8",
                "bg": "rgba(56, 189, 248, 0.15)",
                "border": "rgba(56, 189, 248, 0.4)",
                "icon": "⚡"
            }
        else:
            return {
                "label": "Declined",
                "color": "#ef4444",
                "bg": "rgba(239, 68, 68, 0.15)",
                "border": "rgba(239, 68, 68, 0.4)",
                "icon": "✕"
            }


class PixelRewardConfig(models.Model):
    """
    Master Data & Administrative Configuration:
    Defines how many pixels are allotted and awarded for each habit classification:
    1. User-Defined Habits (GENERAL / Honor System)
    2. Predefined Purposeful Habits (PREDEFINED_PURPOSE)
    3. Expert Prescribed Habits (EXPERT_PRESCRIBED)

    Enables administrators to adjust accomplishment rewards dynamically across the platform.
    """
    DEFAULT_USER_DEFINED = 2
    DEFAULT_PREDEFINED = 5
    DEFAULT_EXPERT_PRESCRIBED = 10

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pixel_reward_configs",
        help_text="Workspace scope (null for system-wide global configuration)",
    )
    user_defined_pixels = models.PositiveIntegerField(
        default=DEFAULT_USER_DEFINED,
        help_text="Pixels awarded per accomplishment for user-defined personal habits",
    )
    predefined_pixels = models.PositiveIntegerField(
        default=DEFAULT_PREDEFINED,
        help_text="Pixels awarded per accomplishment for predefined purposeful habits",
    )
    expert_prescribed_pixels = models.PositiveIntegerField(
        default=DEFAULT_EXPERT_PRESCRIBED,
        help_text="Pixels awarded per accomplishment for expert prescribed habits",
    )
    auto_sync_active_habits = models.BooleanField(
        default=True,
        help_text="Automatically update existing active habits to match newly configured pixel rates.",
    )

    # Dynamic Verification Layer Bonus Adders
    bonus_time_window = models.PositiveIntegerField(
        default=2,
        help_text="Bonus pixels awarded for adhering to a strict daily time window",
    )
    bonus_location = models.PositiveIntegerField(
        default=3,
        help_text="Bonus pixels awarded for physical presence at a geofenced location",
    )
    bonus_duration = models.PositiveIntegerField(
        default=2,
        help_text="Bonus pixels awarded for verified session/workout duration",
    )
    bonus_numeric_target = models.PositiveIntegerField(
        default=2,
        help_text="Bonus pixels awarded for achieving a quantitative numerical metric target",
    )
    bonus_evidence_proof = models.PositiveIntegerField(
        default=3,
        help_text="Bonus pixels awarded for submitting verified proof of work (photo/document)",
    )

    def calculate_bonuses(self, habit) -> int:
        """Calculates sum of bonus pixels for active verification layers."""
        bonuses = 0
        if getattr(habit, "has_time_window", False):
            bonuses += self.bonus_time_window
        if getattr(habit, "is_location_restricted", False):
            bonuses += self.bonus_location
        if getattr(habit, "requires_duration", False):
            bonuses += self.bonus_duration
        if getattr(habit, "requires_numeric", False):
            bonuses += self.bonus_numeric_target
        if getattr(habit, "requires_evidence", False):
            bonuses += self.bonus_evidence_proof
        return bonuses

    def calculate_habit_pixels(self, habit):
        """
        Calculates dynamic total pixel score based on base habit classification
        plus any active modular verification bonuses.
        """
        base = self.user_defined_pixels
        if habit.habit_type == Habit.HabitType.PREDEFINED_PURPOSE:
            base = self.predefined_pixels
        elif habit.habit_type == Habit.HabitType.EXPERT_PRESCRIBED:
            base = self.expert_prescribed_pixels

        return base + self.calculate_bonuses(habit)
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Administrative notes or rationale for these reward thresholds",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_pixel_configs",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Pixel Reward Configuration"
        verbose_name_plural = "Pixel Reward Configurations"

    def __str__(self):
        scope = self.tenant.name if self.tenant else "Global"
        return f"PixelRewardConfig ({scope}): User={self.user_defined_pixels} Px, Predefined={self.predefined_pixels} Px, Expert={self.expert_prescribed_pixels} Px"

    @classmethod
    def get_config(cls, tenant=None):
        """
        Retrieves the active pixel reward configuration for the tenant,
        falling back to global configuration if tenant-specific does not exist.
        Initializes default record if neither exists.
        """
        try:
            if tenant:
                cfg = cls.objects.filter(tenant=tenant).first()
                if cfg:
                    return cfg
            global_cfg = cls.objects.filter(tenant__isnull=True).first()
            if global_cfg:
                return global_cfg
            # Create default global config
            return cls.objects.create(
                user_defined_pixels=cls.DEFAULT_USER_DEFINED,
                predefined_pixels=cls.DEFAULT_PREDEFINED,
                expert_prescribed_pixels=cls.DEFAULT_EXPERT_PRESCRIBED,
                notes="System initial default reward configuration.",
            )
        except Exception:
            # Fallback during initial migrations or isolated mock runs
            return cls(
                user_defined_pixels=cls.DEFAULT_USER_DEFINED,
                predefined_pixels=cls.DEFAULT_PREDEFINED,
                expert_prescribed_pixels=cls.DEFAULT_EXPERT_PRESCRIBED,
            )

    def get_pixel_for_type(self, habit_type):
        """
        Returns the configured pixel award for a given Habit.HabitType.
        """
        if habit_type == Habit.HabitType.EXPERT_PRESCRIBED:
            return self.expert_prescribed_pixels
        elif habit_type == Habit.HabitType.PREDEFINED_PURPOSE:
            return self.predefined_pixels
        return self.user_defined_pixels

    def sync_to_habits(self, tenant=None):
        """
        Synchronizes all active habits and templates to reflect the updated pixel allocations.
        """
        filter_kwargs = {}
        if tenant:
            filter_kwargs["tenant"] = tenant

        u_count = Habit.objects.filter(habit_type=Habit.HabitType.GENERAL, **filter_kwargs).update(
            pixel_score=self.user_defined_pixels
        )
        p_count = Habit.objects.filter(habit_type=Habit.HabitType.PREDEFINED_PURPOSE, **filter_kwargs).update(
            pixel_score=self.predefined_pixels
        )
        e_count = Habit.objects.filter(habit_type=Habit.HabitType.EXPERT_PRESCRIBED, **filter_kwargs).update(
            pixel_score=self.expert_prescribed_pixels
        )
        return {
            "user_defined": u_count,
            "predefined": p_count,
            "expert": e_count,
            "total": u_count + p_count + e_count,
        }


def seed_default_categories():
    """
    Seeds baseline system-wide Habit Categories if not present.
    Common for all users and workspaces across the platform.
    Idempotent: skips existing entries.
    """
    default_categories = [
        {"name": "Health", "icon": "🍎", "color": "#10b981", "description": "Physical health, nutrition, and well-being."},
        {"name": "Fitness", "icon": "🏋️", "color": "#f59e0b", "description": "Exercise, workouts, and athletic training."},
        {"name": "Learning", "icon": "📚", "color": "#6366f1", "description": "Reading, studying, coding, and skill development."},
        {"name": "Productivity", "icon": "⚡", "color": "#3b82f6", "description": "Work habits, focus routines, and organization."},
        {"name": "Personal Development", "icon": "🌱", "color": "#ec4899", "description": "Mindfulness, meditation, journaling, and self-improvement."},
        {"name": "Other", "icon": "📌", "color": "#8b5cf6", "description": "General habits and hobbies."},
    ]
    for cat in default_categories:
        HabitCategory.objects.get_or_create(
            name=cat["name"],
            defaults={
                "icon": cat["icon"],
                "color": cat["color"],
                "description": cat["description"],
                "is_active": True,
            },
        )


def seed_default_master_data_for_tenant(tenant=None):
    """
    Seeds baseline master data (Categories, Rule Strategies, and Catalog Templates) if not present.
    Maintains backward compatibility while ensuring master data is system-wide.
    """
    seed_default_categories()
    seed_default_rule_strategies()
    seed_default_catalog_habits(tenant=tenant)


def seed_default_rule_strategies():
    """
    Seeds baseline system-wide Rule Strategies managed by the tech team.
    Common for all users and workspaces across the platform.
    Idempotent: skips existing entries.
    """
    default_rules = [
        {
            "name": "Honor System (One-Click)",
            "engine_type": RuleStrategy.EngineType.STANDARD,
            "description": "Standard honor system. Check off habit with a single tap.",
        },
        {
            "name": "Time Window Constrained",
            "engine_type": RuleStrategy.EngineType.TIME_WINDOW,
            "description": "Can only be completed within a defined daily time window.",
        },
        {
            "name": "Proof Required (Image/Doc)",
            "engine_type": RuleStrategy.EngineType.EVIDENCE_FILE,
            "description": "Requires uploading an image or document as proof of completion.",
        },
        {
            "name": "Quantitative Goal",
            "engine_type": RuleStrategy.EngineType.NUMERIC_TARGET,
            "description": "Requires logging a numeric value that reaches or exceeds your target.",
        },
        {
            "name": "Time Window + Proof Required",
            "engine_type": RuleStrategy.EngineType.TIME_AND_EVIDENCE,
            "description": "Requires completing within a time window AND uploading proof.",
        },
    ]
    for rule in default_rules:
        RuleStrategy.objects.get_or_create(
            name=rule["name"],
            defaults={
                "engine_type": rule["engine_type"],
                "description": rule["description"],
                "is_active": True,
            },
        )


def seed_default_catalog_habits(creator=None, tenant=None):
    """
    Seeds curated catalog template habits for:
    1. Predefined Purposeful Habits (e.g. Gym, Wake-up, Hydration, Deep Work)
    2. Expert Prescribed Habits
    Available for all users to add to their personal habit tracking lists.
    Loads dynamically from habits/fixtures/default_catalog_templates.json.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if creator is None:
        creator = User.objects.filter(is_superuser=True).first() or User.objects.first()

    if not creator:
        return

    from .services import import_catalog_templates_from_file
    import_catalog_templates_from_file(creator=creator)
