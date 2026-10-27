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
    Strictly tenant-scoped.
    """
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="habit_categories",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=20, blank=True, default="📁", help_text="Emoji or icon symbol")
    color = models.CharField(max_length=30, blank=True, default="#38bdf8", help_text="Badge color hex")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("tenant", "name")]
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
    Strictly tenant-scoped.
    """
    class EngineType(models.TextChoices):
        STANDARD = "STANDARD", "Honor System (One-Click)"
        TIME_WINDOW = "TIME_WINDOW", "Time Window Constrained"
        EVIDENCE_FILE = "EVIDENCE_FILE", "Proof Required (Image/Doc)"
        NUMERIC_TARGET = "NUMERIC_TARGET", "Quantitative Goal"
        TIME_AND_EVIDENCE = "TIME_AND_EVIDENCE", "Time Window + Proof Required"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="rule_strategies",
    )
    name = models.CharField(max_length=120)
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
        unique_together = [("tenant", "name")]
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

        # Pixel Score Rules Validation
        if self.habit_type == self.HabitType.GENERAL:
            if self.pixel_score is not None and self.pixel_score != 2:
                errors["pixel_score"] = "User-created personal habits have a fixed pixel score of 2."
        else:
            if self.pixel_score is not None and self.pixel_score < 1:
                errors["pixel_score"] = "Pixel score must be at least 1."

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

    def save(self, *args, **kwargs):
        # 1. Synchronize category and category_ref
        if self.category and self.tenant_id:
            if not self.category_ref or self.category_ref.name != self.category:
                cat, _ = HabitCategory.objects.get_or_create(
                    tenant=self.tenant,
                    name=self.category,
                    defaults={"is_active": True},
                )
                self.category_ref = cat
        elif self.category_ref:
            self.category = self.category_ref.name

        # 2. Synchronize validation_rule and rule_strategy_ref
        if self.validation_rule and self.tenant_id:
            if not self.rule_strategy_ref or self.rule_strategy_ref.engine_type != self.validation_rule:
                strat = RuleStrategy.objects.filter(
                    tenant=self.tenant,
                    engine_type=self.validation_rule,
                ).first()
                if not strat:
                    label = dict(self.ValidationRule.choices).get(self.validation_rule, self.validation_rule)
                    strat, _ = RuleStrategy.objects.get_or_create(
                        tenant=self.tenant,
                        name=label,
                        defaults={
                            "engine_type": self.validation_rule,
                            "is_active": True,
                        },
                    )
                self.rule_strategy_ref = strat
        elif self.rule_strategy_ref:
            self.validation_rule = self.rule_strategy_ref.engine_type

        # 3. Enforce pixel score rules
        if self.habit_type == self.HabitType.GENERAL:
            self.pixel_score = 2
        elif not self.pixel_score or self.pixel_score < 1:
            if self.habit_type == self.HabitType.PREDEFINED_PURPOSE:
                self.pixel_score = 5
            elif self.habit_type == self.HabitType.EXPERT_PRESCRIBED:
                self.pixel_score = 10
            else:
                self.pixel_score = 2

        super().save(*args, **kwargs)

    @property
    def pixel_badge(self):
        return {
            "score": self.pixel_score,
            "label": f"{self.pixel_score} Px",
            "full_label": f"{self.pixel_score} Pixels",
        }

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


def seed_default_master_data_for_tenant(tenant):
    """
    Seeds baseline master data (Categories and Rule Strategies) for a tenant if not present.
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
            tenant=tenant,
            name=cat["name"],
            defaults={
                "icon": cat["icon"],
                "color": cat["color"],
                "description": cat["description"],
                "is_active": True,
            },
        )

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
            tenant=tenant,
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
    1. Predefined Purposeful Habits
    2. Expert Prescribed Habits
    Available for all users to add to their personal habit tracking lists.
    """
    if Habit.objects.filter(is_template=True).exists():
        return

    from django.contrib.auth import get_user_model
    User = get_user_model()
    if creator is None:
        creator = User.objects.filter(is_superuser=True).first() or User.objects.first()

    if not creator:
        return

    predefined_templates = [
        {
            "name": "Daily Deep Hydration",
            "category": "Health",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "description": "Maintain optimal physical hydration and cognitive performance by consuming at least 2 liters of pure water daily.",
            "frequency": Habit.Frequency.DAILY,
            "validation_rule": Habit.ValidationRule.NUMERIC_TARGET,
            "target_value": 2.0,
            "unit_label": "Liters",
        },
        {
            "name": "Deep Work Sprint (45 Mins)",
            "category": "Productivity",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "description": "Dedicated 45-minute distraction-free focus block on highest priority project or technical coding problem.",
            "frequency": Habit.Frequency.DAILY,
            "validation_rule": Habit.ValidationRule.NUMERIC_TARGET,
            "target_value": 45,
            "unit_label": "Mins",
        },
        {
            "name": "Morning Mobility & Core Routine",
            "category": "Fitness",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "description": "Complete morning stretching, joint mobility, and spine activation between 5:30 AM and 9:00 AM.",
            "frequency": Habit.Frequency.DAILY,
            "validation_rule": Habit.ValidationRule.TIME_WINDOW,
            "window_start_time": "05:30:00",
            "window_end_time": "09:00:00",
        },
    ]

    expert_templates = [
        {
            "name": "Cardiologist-Approved Zone 2 Cardio",
            "category": "Fitness",
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "description": "Clinical aerobic base protocol: 30 minutes of Zone 2 steady-state exercise to improve cardiac output and mitochondrial health.",
            "frequency": Habit.Frequency.WEEKDAYS,
            "selected_weekdays": [0, 2, 4],  # Mon, Wed, Fri
            "validation_rule": Habit.ValidationRule.NUMERIC_TARGET,
            "target_value": 30,
            "unit_label": "Mins",
        },
        {
            "name": "Circadian Light Exposure Protocol",
            "category": "Health",
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "description": "Neurobiology circadian reset: View natural sunlight outdoors within 60 minutes of waking (6:00 AM - 8:30 AM) to optimize cortisol and sleep cycles.",
            "frequency": Habit.Frequency.DAILY,
            "validation_rule": Habit.ValidationRule.TIME_WINDOW,
            "window_start_time": "06:00:00",
            "window_end_time": "08:30:00",
        },
        {
            "name": "Deliberate Non-Fiction Reading",
            "category": "Learning",
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "description": "Cognitive development protocol: Complete 20 pages of technical, philosophical, or educational reading daily.",
            "frequency": Habit.Frequency.DAILY,
            "validation_rule": Habit.ValidationRule.NUMERIC_TARGET,
            "target_value": 20,
            "unit_label": "Pages",
        },
    ]

    for item in predefined_templates + expert_templates:
        Habit.objects.create(
            tenant=tenant,
            created_by=creator,
            name=item["name"],
            category=item["category"],
            habit_type=item["habit_type"],
            description=item["description"],
            frequency=item["frequency"],
            selected_weekdays=item.get("selected_weekdays", []),
            validation_rule=item["validation_rule"],
            target_value=item.get("target_value"),
            unit_label=item.get("unit_label", ""),
            window_start_time=item.get("window_start_time"),
            window_end_time=item.get("window_end_time"),
            pixel_score=5 if item["habit_type"] == Habit.HabitType.PREDEFINED_PURPOSE else 10,
            is_template=True,
            is_active=True,
        )


