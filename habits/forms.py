import uuid
from django import forms
from django.utils import timezone
from .models import Habit, HabitCategory, HabitCompletion, PixelRewardConfig, RuleStrategy
from .validators import HabitCompletionValidationEngine


class HabitCategoryForm(forms.ModelForm):
    """
    Form for creating and editing Master Data Habit Categories.
    Strictly tenant-scoped.
    """
    class Meta:
        model = HabitCategory
        fields = ["name", "icon", "color", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., Health, Learning, Career, Fitness",
                "autofocus": True,
            }),
            "icon": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., 🍎, 📚, ⚡, 🧘, 💻",
            }),
            "color": forms.TextInput(attrs={
                "class": "form-control",
                "type": "color",
                "style": "height: 42px; width: 90px; padding: 2px;",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Brief description of habits under this category...",
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop("tenant", None)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Category name cannot be empty.")
        qs = HabitCategory.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"A habit category named '{name}' already exists.")
        return name


class RuleStrategyForm(forms.ModelForm):
    """
    Form for creating and editing Master Data Rule Strategies.
    Common master data managed by the tech team.
    """
    class Meta:
        model = RuleStrategy
        fields = ["name", "engine_type", "default_unit", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., Morning Time-Window, 5km Run Metric, Photo Verification",
                "autofocus": True,
            }),
            "engine_type": forms.Select(attrs={
                "class": "form-control",
                "id": "id_engine_type",
            }),
            "default_unit": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., mins, km, pages, reps",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Detailed guidelines and expectations for this strategy...",
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop("tenant", None)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Rule strategy name cannot be empty.")
        qs = RuleStrategy.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"A rule strategy named '{name}' already exists.")
        return name


class HabitForm(forms.ModelForm):
    """
    Form for creating and editing habits.
    Integrates dynamically with Master Data (HabitCategory & RuleStrategy).
    Maintains full backward compatibility with legacy category & validation_rule fields.
    """
    WEEKDAY_CHOICES = [
        ("0", "Mon"),
        ("1", "Tue"),
        ("2", "Wed"),
        ("3", "Thu"),
        ("4", "Fri"),
        ("5", "Sat"),
        ("6", "Sun"),
    ]

    weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "weekday-checkbox"}),
        required=False,
        label="Select Scheduled Days",
        help_text="Required when frequency is set to 'Selected Days of the Week'.",
    )
    target_days_per_week = forms.TypedChoiceField(
        choices=Habit.WEEKLY_TARGET_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
        widget=forms.Select(attrs={
            "class": "form-control",
            "id": "id_target_days_per_week",
            "style": "font-weight: 600;",
        }),
        label="Target Days per Week",
        help_text="Choose how many days per week you commit to achieving this habit (1-7 days).",
    )
    idempotency_key = forms.CharField(
        widget=forms.HiddenInput(),
        required=False,
    )

    class Meta:
        model = Habit
        fields = [
            "name",
            "idempotency_key",
            "habit_type",
            "is_template",
            "pixel_score",
            "description",
            "category_ref",
            "category",
            "rule_strategy_ref",
            "frequency",
            "target_days_per_week",
            "selected_weekdays",
            "start_date",
            "is_active",
            "validation_rule",
            "window_start_time",
            "window_end_time",
            "target_value",
            "unit_label",
            "is_location_restricted",
            "location_name",
            "target_latitude",
            "target_longitude",
            "allowed_radius_meters",
            "enable_time_window",
            "enable_numeric_target",
            "enable_evidence_upload",
            "enable_duration_requirement",
            "min_duration_minutes",
            "enable_ai_proof_verification",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., Read 20 mins, Run 5km, Morning Meditation",
                "autofocus": True,
            }),
            "habit_type": forms.Select(attrs={
                "class": "form-control",
                "id": "id_habit_type",
            }),
            "is_template": forms.CheckboxInput(attrs={
                "class": "form-check-input",
                "id": "id_is_template",
            }),
            "pixel_score": forms.NumberInput(attrs={
                "class": "form-control",
                "id": "id_pixel_score",
                "min": "1",
                "placeholder": "e.g., 2, 5, 10",
                "style": "max-width: 140px; font-weight: 700;",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional details, guidelines, or motivation...",
            }),
            "category_ref": forms.Select(attrs={
                "class": "form-control",
                "id": "id_category_ref",
            }),
            "category": forms.HiddenInput(),
            "rule_strategy_ref": forms.Select(attrs={
                "class": "form-control",
                "id": "id_rule_strategy_ref",
            }),
            "frequency": forms.Select(attrs={"class": "form-control", "id": "id_frequency"}),
            "selected_weekdays": forms.HiddenInput(),
            "start_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "validation_rule": forms.Select(attrs={
                "class": "form-control",
                "id": "id_validation_rule",
            }),
            "window_start_time": forms.TimeInput(attrs={
                "class": "form-control",
                "type": "time",
                "id": "id_window_start_time",
            }),
            "window_end_time": forms.TimeInput(attrs={
                "class": "form-control",
                "type": "time",
                "id": "id_window_end_time",
            }),
            "target_value": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "any",
                "placeholder": "e.g., 30, 2.5, 10",
                "id": "id_target_value",
            }),
            "unit_label": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., mins, km, pages, liters, reps",
                "id": "id_unit_label",
            }),
            "idempotency_key": forms.HiddenInput(attrs={"id": "id_idempotency_key"}),
            "is_location_restricted": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_is_location_restricted"}),
            "location_name": forms.TextInput(attrs={"class": "form-control", "id": "id_location_name", "placeholder": "e.g. Gold's Gym Indiranagar, Anytime Fitness, Central Park"}),
            "target_latitude": forms.NumberInput(attrs={"class": "form-control", "id": "id_target_latitude", "step": "any", "placeholder": "e.g. 12.971598"}),
            "target_longitude": forms.NumberInput(attrs={"class": "form-control", "id": "id_target_longitude", "step": "any", "placeholder": "e.g. 77.594566"}),
            "allowed_radius_meters": forms.NumberInput(attrs={"class": "form-control", "id": "id_allowed_radius_meters", "min": "10", "placeholder": "150"}),
            "enable_time_window": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_enable_time_window"}),
            "enable_numeric_target": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_enable_numeric_target"}),
            "enable_evidence_upload": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_enable_evidence_upload"}),
            "enable_duration_requirement": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_enable_duration_requirement"}),
            "min_duration_minutes": forms.NumberInput(attrs={"class": "form-control", "id": "id_min_duration_minutes", "placeholder": "e.g. 45", "min": 1}),
            "enable_ai_proof_verification": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_enable_ai_proof_verification"}),
        }

    def __init__(self, *args, tenant=None, user=None, habit_type_initial=None, is_template_initial=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        self.user = user
        if not self.tenant and self.instance and self.instance.pk and hasattr(self.instance, "tenant"):
            self.tenant = self.instance.tenant

        if not self.instance.pk and not self.initial.get("idempotency_key"):
            self.initial["idempotency_key"] = uuid.uuid4().hex

        self.fields["category_ref"].required = False
        self.fields["category"].required = False
        self.fields["rule_strategy_ref"].required = False
        self.fields["validation_rule"].required = False
        self.fields["selected_weekdays"].required = False
        self.fields["window_start_time"].required = False
        self.fields["window_end_time"].required = False
        self.fields["target_value"].required = False
        self.fields["unit_label"].required = False
        self.fields["habit_type"].required = False
        self.fields["is_template"].required = False
        self.fields["is_location_restricted"].required = False
        self.fields["location_name"].required = False
        self.fields["target_latitude"].required = False
        self.fields["target_longitude"].required = False
        self.fields["allowed_radius_meters"].required = False
        self.fields["is_location_restricted"].label = "Location Verification (Geofenced)"
        self.fields["location_name"].label = "Location / Venue Name"
        self.fields["target_latitude"].label = "Target Latitude"
        self.fields["target_longitude"].label = "Target Longitude"
        self.fields["allowed_radius_meters"].label = "Allowed Radius (Meters)"
        if not self.instance.pk and "allowed_radius_meters" not in self.initial:
            self.initial["allowed_radius_meters"] = 150
        self.fields["name"].label = "Habit Name"
        self.fields["category_ref"].label = "Category"
        self.fields["rule_strategy_ref"].label = "Rule Strategy"
        self.fields["target_value"].label = "Minimum Target Value"
        self.fields["unit_label"].label = "Unit Label"
        self.fields["window_start_time"].label = "Earliest Start Time"
        self.fields["window_end_time"].label = "Latest End Time"
        self.fields["habit_type"].label = "Habit Classification"
        self.fields["is_template"].label = "Publish to System Catalog"
        self.fields["pixel_score"].label = "Allotted Pixel Score"
        self.fields["pixel_score"].required = False
        self.fields["frequency"].label = "Frequency"
        self.fields["start_date"].label = "Start Date"
        self.fields["is_active"].label = "Active Habit"
        self.fields["target_days_per_week"].label = "Target Days per Week"
        self.fields["target_days_per_week"].required = False
        if self.instance and self.instance.pk and self.instance.target_days_per_week:
            self.initial["target_days_per_week"] = self.instance.target_days_per_week
        elif "target_days_per_week" not in self.initial:
            self.initial["target_days_per_week"] = 3

        is_admin_or_tech = bool(self.user and (self.user.is_super_admin or self.user.is_technical_user))

        # Determine effective habit type for defaults
        current_type = (
            habit_type_initial
            or (self.instance.habit_type if self.instance and self.instance.pk else None)
            or self.initial.get("habit_type")
            or Habit.HabitType.GENERAL
        )

        reward_config = PixelRewardConfig.get_config(self.tenant)

        # Set initial pixel_score
        if self.instance and self.instance.pk and self.instance.pixel_score:
            self.initial["pixel_score"] = self.instance.pixel_score
        elif "pixel_score" not in self.initial:
            self.initial["pixel_score"] = reward_config.get_pixel_for_type(current_type)

        if not is_admin_or_tech:
            # Standard users can only create General habits with configured user-defined pixels
            self.fields["habit_type"].choices = [
                (Habit.HabitType.GENERAL, "General Habit (Honor System)"),
            ]
            self.fields["habit_type"].initial = Habit.HabitType.GENERAL
            self.fields["is_template"].initial = False
            self.fields["is_template"].widget = forms.HiddenInput()
            self.fields["pixel_score"].initial = reward_config.user_defined_pixels
            self.fields["pixel_score"].widget = forms.HiddenInput()
        else:
            if habit_type_initial:
                self.initial["habit_type"] = habit_type_initial
            if is_template_initial is not None:
                self.initial["is_template"] = is_template_initial
            elif habit_type_initial in [Habit.HabitType.PREDEFINED_PURPOSE, Habit.HabitType.EXPERT_PRESCRIBED]:
                self.initial["is_template"] = True

        self.fields["category_ref"].queryset = HabitCategory.objects.filter(is_active=True)
        self.fields["rule_strategy_ref"].queryset = RuleStrategy.objects.filter(is_active=True)

        if not self.instance.pk:
            if not self.initial.get("rule_strategy_ref"):
                default_strat = RuleStrategy.objects.filter(
                    engine_type=RuleStrategy.EngineType.STANDARD
                ).first()
                if default_strat:
                    self.initial["rule_strategy_ref"] = default_strat
            if not self.initial.get("validation_rule"):
                self.initial["validation_rule"] = Habit.ValidationRule.STANDARD
            if not self.initial.get("start_date"):
                self.initial["start_date"] = timezone.localdate()
                self.initial["is_active"] = True

        if self.instance.pk and self.instance.selected_weekdays:
            self.initial["weekdays"] = [str(d) for d in self.instance.selected_weekdays]

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Habit name cannot be empty.")

        is_template = bool(
            (hasattr(self, "data") and self.data.get("is_template") in ["on", "true", "True", "1", True])
            or self.cleaned_data.get("is_template")
            or self.initial.get("is_template")
            or getattr(self.instance, "is_template", False)
        )

        if self.tenant:
            qs = Habit.objects.filter(
                tenant=self.tenant,
                name__iexact=name,
                is_active=True,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            # If habit with same idempotency_key already exists in DB, this is an idempotent re-submission
            idempotency_key = self.data.get("idempotency_key", "").strip() if hasattr(self, "data") else ""
            if idempotency_key and qs.filter(idempotency_key=idempotency_key).exists():
                return name

            # Allow recent rapid submissions (within 15s) to pass through so the view can handle them idempotently
            if qs.filter(created_at__gte=timezone.now() - timezone.timedelta(seconds=15)).exists():
                return name

            qs = qs.filter(is_template=is_template)
            if qs.exists():
                entity_label = "catalog template" if is_template else "active habit"
                raise forms.ValidationError(f"An {entity_label} named '{name}' already exists in your workspace.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        frequency = cleaned_data.get("frequency")
        weekdays = cleaned_data.get("weekdays") or []

        # 1. Resolve Category
        category_ref = cleaned_data.get("category_ref")
        if category_ref:
            cleaned_data["category"] = category_ref.name
        elif cleaned_data.get("category"):
            cat, _ = HabitCategory.objects.get_or_create(
                name=cleaned_data.get("category"),
                defaults={"is_active": True},
            )
            cleaned_data["category_ref"] = cat
            cleaned_data["category"] = cat.name

        # 2. Resolve Rule Strategy & Template Designation
        rule_strategy_ref = cleaned_data.get("rule_strategy_ref")
        habit_type = cleaned_data.get("habit_type") or Habit.HabitType.GENERAL
        is_admin_or_tech = bool(self.user and (self.user.is_super_admin or self.user.is_technical_user))
        if not is_admin_or_tech:
            cleaned_data["habit_type"] = Habit.HabitType.GENERAL
            cleaned_data["is_template"] = False
        else:
            cleaned_data["habit_type"] = habit_type
            cleaned_data["is_template"] = bool(cleaned_data.get("is_template", False))

        is_template = cleaned_data.get("is_template", False)

        # 3. Purpose-oriented duplicate restriction for user-defined habits:
        if not is_template and getattr(self.instance, "template_source_id", None) is None:
            name = cleaned_data.get("name", "").strip()
            is_new = (self.instance.pk is None)
            name_changed = bool(self.instance.pk and self.instance.name.strip().lower() != name.lower())
            if (is_new or name_changed) and name:
                from .services import find_matching_predefined_template
                desc = cleaned_data.get("description", "")
                matched_template = find_matching_predefined_template(name, desc)
                if matched_template and matched_template.pk != getattr(self.instance, "pk", None):
                    self.add_error(
                        "name",
                        f"A standardized predefined habit for this purpose already exists in the library: '{matched_template.name}'. "
                        f"Creating duplicate custom habits for existing predefined purposes is restricted to optimize database space and performance. "
                        f"Please adopt and personalize '{matched_template.name}' from the Catalog instead, where you can customize your personal schedule and timing."
                    )

        if rule_strategy_ref:
            rule = rule_strategy_ref.engine_type
            cleaned_data["validation_rule"] = rule
        else:
            rule = cleaned_data.get("validation_rule") or Habit.ValidationRule.STANDARD
            cleaned_data["validation_rule"] = rule
            strat = RuleStrategy.objects.filter(engine_type=rule).first()
            if strat:
                cleaned_data["rule_strategy_ref"] = strat

        start_time = cleaned_data.get("window_start_time")
        end_time = cleaned_data.get("window_end_time")
        target_value = cleaned_data.get("target_value")
        unit_label = cleaned_data.get("unit_label")

        # Frequency validation
        if frequency == Habit.Frequency.WEEKDAYS:
            if not weekdays:
                self.add_error("weekdays", "Please select at least one day of the week.")
                cleaned_data["selected_weekdays"] = []
            else:
                try:
                    chosen = [int(w) for w in weekdays]
                    cleaned_data["selected_weekdays"] = chosen
                    self.instance.selected_weekdays = chosen
                except ValueError:
                    self.add_error("weekdays", "Invalid weekday selection.")
        elif frequency == Habit.Frequency.WEEKLY_TARGET:
            target_days = cleaned_data.get("target_days_per_week")
            if not target_days:
                target_days = 3
                cleaned_data["target_days_per_week"] = 3
            try:
                target_days_int = int(target_days)
                if not (1 <= target_days_int <= 7):
                    self.add_error("target_days_per_week", "Please select a target between 1 and 7 days per week.")
                else:
                    cleaned_data["target_days_per_week"] = target_days_int
                    self.instance.target_days_per_week = target_days_int
            except (ValueError, TypeError):
                self.add_error("target_days_per_week", "Invalid weekly target selection.")
            cleaned_data["selected_weekdays"] = [0, 1, 2, 3, 4, 5, 6]
            self.instance.selected_weekdays = [0, 1, 2, 3, 4, 5, 6]
        else:
            cleaned_data["selected_weekdays"] = [0, 1, 2, 3, 4, 5, 6]
            self.instance.selected_weekdays = [0, 1, 2, 3, 4, 5, 6]

        # Validation Rule cross-field checks
        if rule in [Habit.ValidationRule.TIME_WINDOW, Habit.ValidationRule.TIME_AND_EVIDENCE]:
            if not start_time:
                self.add_error("window_start_time", "Window start time is required for time-constrained habits.")
            if not end_time:
                self.add_error("window_end_time", "Window end time is required for time-constrained habits.")
            if start_time and end_time and start_time >= end_time:
                self.add_error("window_end_time", "Window end time must be later than window start time.")

        if rule == Habit.ValidationRule.NUMERIC_TARGET:
            if target_value is None or target_value <= 0:
                self.add_error("target_value", "Please enter a target number greater than zero.")
            if not unit_label or not unit_label.strip():
                self.add_error("unit_label", "Please specify a unit label (e.g. mins, km, pages).")

        # Location Geofencing cross-field checks
        is_loc = cleaned_data.get("is_location_restricted", False)
        if is_loc:
            t_lat = cleaned_data.get("target_latitude")
            t_lng = cleaned_data.get("target_longitude")
            radius = cleaned_data.get("allowed_radius_meters")
            if t_lat is None:
                self.add_error("target_latitude", "Target latitude is required when location geofencing is enabled.")
            elif not (-90.0 <= float(t_lat) <= 90.0):
                self.add_error("target_latitude", "Latitude must be between -90 and +90 degrees.")

            if t_lng is None:
                self.add_error("target_longitude", "Target longitude is required when location geofencing is enabled.")
            elif not (-180.0 <= float(t_lng) <= 180.0):
                self.add_error("target_longitude", "Longitude must be between -180 and +180 degrees.")

            if radius is not None and int(radius) < 10:
                self.add_error("allowed_radius_meters", "Allowed radius must be at least 10 meters.")

        # 3. Pixel Score Validation & Enforcement via dynamic Admin Configuration
        reward_config = PixelRewardConfig.get_config(self.tenant)
        if habit_type == Habit.HabitType.GENERAL or not is_admin_or_tech:
            cleaned_data["pixel_score"] = reward_config.user_defined_pixels
            self.instance.pixel_score = reward_config.user_defined_pixels
        else:
            score = cleaned_data.get("pixel_score")
            if score is None or score == "":
                default_score = reward_config.get_pixel_for_type(habit_type)
                cleaned_data["pixel_score"] = default_score
                self.instance.pixel_score = default_score
            else:
                try:
                    int_score = int(score)
                    if int_score < 1:
                        self.add_error("pixel_score", "Pixel score must be at least 1.")
                    else:
                        cleaned_data["pixel_score"] = int_score
                        self.instance.pixel_score = int_score
                except (ValueError, TypeError):
                    self.add_error("pixel_score", "Invalid pixel score value.")

        return cleaned_data

    def save(self, commit=True):
        habit = super().save(commit=False)
        if self.tenant and not habit.tenant_id:
            habit.tenant = self.tenant
        if self.user and not habit.created_by_id:
            habit.created_by = self.user
        habit.habit_type = self.cleaned_data.get("habit_type") or habit.habit_type or Habit.HabitType.GENERAL
        habit.is_template = bool(self.cleaned_data.get("is_template", False))
        habit.pixel_score = self.cleaned_data.get("pixel_score") or PixelRewardConfig.get_config(self.tenant).user_defined_pixels
        habit.selected_weekdays = self.cleaned_data.get("selected_weekdays", [])
        if self.cleaned_data.get("category_ref"):
            habit.category_ref = self.cleaned_data["category_ref"]
            habit.category = habit.category_ref.name
        elif self.cleaned_data.get("category"):
            habit.category = self.cleaned_data["category"]

        if self.cleaned_data.get("rule_strategy_ref"):
            habit.rule_strategy_ref = self.cleaned_data["rule_strategy_ref"]
            habit.validation_rule = habit.rule_strategy_ref.engine_type
        elif self.cleaned_data.get("validation_rule"):
            habit.validation_rule = self.cleaned_data["validation_rule"]

        idempotency_key = self.cleaned_data.get("idempotency_key")
        if idempotency_key and not habit.idempotency_key:
            habit.idempotency_key = idempotency_key

        if commit:
            habit.save()
        return habit


class HabitCompletionSubmissionForm(forms.ModelForm):
    """
    Handles user submission when completing a habit with evidence, metric value, or notes.
    """
    class Meta:
        model = HabitCompletion
        fields = ["completion_date", "evidence_file", "logged_value", "notes"]
        widgets = {
            "completion_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "evidence_file": forms.FileInput(attrs={"class": "form-control", "accept": ".jpg,.jpeg,.png,.webp,.pdf"}),
            "logged_value": forms.NumberInput(attrs={"class": "form-control", "step": "any", "placeholder": "Enter your logged metric"}),
            "notes": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional note or reflection..."}),
        }

    def __init__(self, *args, habit=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.habit = habit
        self.fields["completion_date"].required = False
        self.fields["evidence_file"].required = False
        self.fields["logged_value"].required = False
        self.fields["notes"].required = False

        if habit:
            if habit.requires_evidence:
                self.fields["evidence_file"].label = "Proof of Completion (Required)"
                self.fields["evidence_file"].help_text = "Upload JPG, PNG, WEBP, or PDF (max 5 MB)."
            if habit.requires_numeric:
                self.fields["logged_value"].label = f"Progress Metric ({habit.unit_label}) (Target: {habit.target_value})"

    def clean(self):
        cleaned_data = super().clean()
        if not self.habit:
            return cleaned_data

        engine = HabitCompletionValidationEngine()
        errors = engine.validate(self.habit, cleaned_data, self.files)
        if errors:
            for err in errors:
                self.add_error(None, err)

        return cleaned_data


class PixelRewardConfigForm(forms.ModelForm):
    """
    Administrative form for configuring dynamic pixel allocations per habit classification:
    - User-Defined (General)
    - Predefined Purposeful
    - Expert Prescribed
    """
    class Meta:
        model = PixelRewardConfig
        fields = [
            "user_defined_pixels",
            "predefined_pixels",
            "expert_prescribed_pixels",
            "auto_sync_active_habits",
            "notes",
        ]
        widgets = {
            "user_defined_pixels": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "id": "id_user_defined_pixels",
                "style": "font-size: 1.25rem; font-weight: 800; text-align: center; max-width: 140px;",
            }),
            "predefined_pixels": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "id": "id_predefined_pixels",
                "style": "font-size: 1.25rem; font-weight: 800; text-align: center; max-width: 140px;",
            }),
            "expert_prescribed_pixels": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "id": "id_expert_prescribed_pixels",
                "style": "font-size: 1.25rem; font-weight: 800; text-align: center; max-width: 140px;",
            }),
            "auto_sync_active_habits": forms.CheckboxInput(attrs={
                "class": "form-check-input",
                "id": "id_auto_sync_active_habits",
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Optional administrative note or policy reason for this reward rate change...",
            }),
        }
        labels = {
            "user_defined_pixels": "User Defined Habits (General)",
            "predefined_pixels": "Predefined Purposeful Habits",
            "expert_prescribed_pixels": "Expert Prescribed Habits",
            "auto_sync_active_habits": "Sync to existing active habits across workspace",
            "notes": "Policy Notes / Reason for Adjustment",
        }

    def clean_user_defined_pixels(self):
        val = self.cleaned_data.get("user_defined_pixels")
        if val is None or val < 1:
            raise forms.ValidationError("User-defined habit pixels must be at least 1 Px.")
        return val

    def clean_predefined_pixels(self):
        val = self.cleaned_data.get("predefined_pixels")
        if val is None or val < 1:
            raise forms.ValidationError("Predefined purposeful habit pixels must be at least 1 Px.")
        return val

    def clean_expert_prescribed_pixels(self):
        val = self.cleaned_data.get("expert_prescribed_pixels")
        if val is None or val < 1:
            raise forms.ValidationError("Expert prescribed habit pixels must be at least 1 Px.")
        return val


class AdoptHabitPersonalizationForm(forms.Form):
    """
    Form to allow individual users to customize operational parameters
    (e.g., wake-up time window, numeric goal, frequency, weekdays)
    when adopting a standardized predefined or expert-prescribed habit template.
    """
    window_start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time", "id": "id_adopt_window_start_time"}),
        label="Start Time",
        help_text="Earliest time you complete this habit (e.g., wake-up window start).",
    )
    window_end_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time", "id": "id_adopt_window_end_time"}),
        label="End Time",
        help_text="Latest time you complete this habit (e.g., wake-up target deadline).",
    )
    target_value = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "any", "id": "id_adopt_target_value"}),
        label="Target Metric Goal",
        help_text="Quantitative goal to achieve each day (e.g., 2.0 liters, 45 mins).",
    )
    unit_label = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "id_adopt_unit_label"}),
        label="Metric Unit",
        help_text="Unit of measurement (e.g., Liters, Mins, Pages, Steps).",
    )
    target_days_per_week = forms.TypedChoiceField(
        choices=Habit.WEEKLY_TARGET_CHOICES,
        coerce=int,
        empty_value=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_adopt_target_days_per_week", "style": "font-weight: 600;"}),
        label="Weekly Commitment (Days per Week)",
        help_text="Choose how many days per week you plan to achieve this habit (e.g. 3, 4, or 5 days/week for gym).",
    )
    frequency = forms.ChoiceField(
        choices=Habit.Frequency.choices,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_adopt_frequency"}),
        label="Tracking Frequency",
    )
    selected_weekdays = forms.MultipleChoiceField(
        choices=Habit.WEEKDAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        label="Active Days (if Weekdays)",
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date", "id": "id_adopt_start_date"}),
        label="Start Date",
    )
    is_location_restricted = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_adopt_is_location_restricted"}),
        label="Require Physical Location (Geofenced GPS Check-in)",
    )
    location_name = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "id_adopt_location_name", "placeholder": "e.g. Gold's Gym Indiranagar"}),
        label="Venue / Gym Name",
    )
    target_latitude = forms.DecimalField(
        required=False,
        max_digits=9,
        decimal_places=6,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_adopt_target_latitude", "step": "any", "placeholder": "e.g. 12.971598"}),
        label="Target Latitude",
    )
    target_longitude = forms.DecimalField(
        required=False,
        max_digits=9,
        decimal_places=6,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_adopt_target_longitude", "step": "any", "placeholder": "e.g. 77.594566"}),
        label="Target Longitude",
    )
    allowed_radius_meters = forms.IntegerField(
        required=False,
        min_value=10,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_adopt_allowed_radius_meters", "placeholder": "150"}),
        label="Allowed Radius (Meters)",
    )
    enable_time_window = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_adopt_enable_time_window"}),
        label="Time Window Restriction",
    )
    enable_duration_requirement = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_adopt_enable_duration_requirement"}),
        label="Workout / Session Duration",
    )
    min_duration_minutes = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=1440,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_adopt_min_duration_minutes", "placeholder": "e.g. 45"}),
        label="Minimum Duration (Minutes)",
    )
    enable_numeric_target = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_adopt_enable_numeric_target"}),
        label="Quantitative Target Metric",
    )
    enable_evidence_upload = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_adopt_enable_evidence_upload"}),
        label="Proof of Work Upload",
    )
    enable_ai_proof_verification = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_adopt_enable_ai_proof_verification"}),
        label="AI Proof Relevance Verification",
    )

    def __init__(self, *args, template_habit=None, **kwargs):
        self.template_habit = template_habit
        super().__init__(*args, **kwargs)

        if template_habit:
            if not self.is_bound:
                self.fields["frequency"].initial = template_habit.frequency
                self.fields["window_start_time"].initial = template_habit.window_start_time
                self.fields["window_end_time"].initial = template_habit.window_end_time
                self.fields["target_value"].initial = template_habit.target_value
                self.fields["unit_label"].initial = template_habit.unit_label
                self.fields["start_date"].initial = timezone.localdate()
                if template_habit.target_days_per_week:
                    self.fields["target_days_per_week"].initial = template_habit.target_days_per_week
                elif template_habit.frequency == Habit.Frequency.WEEKLY_TARGET:
                    self.fields["target_days_per_week"].initial = 3
                if template_habit.selected_weekdays:
                    self.fields["selected_weekdays"].initial = [str(d) for d in template_habit.selected_weekdays]
                self.fields["is_location_restricted"].initial = template_habit.is_location_restricted
                self.fields["location_name"].initial = template_habit.location_name
                self.fields["target_latitude"].initial = template_habit.target_latitude
                self.fields["target_longitude"].initial = template_habit.target_longitude
                self.fields["allowed_radius_meters"].initial = template_habit.allowed_radius_meters or 150
                self.fields["enable_time_window"].initial = template_habit.has_time_window
                self.fields["enable_duration_requirement"].initial = template_habit.enable_duration_requirement
                self.fields["min_duration_minutes"].initial = template_habit.min_duration_minutes
                self.fields["enable_numeric_target"].initial = template_habit.requires_numeric
                self.fields["enable_evidence_upload"].initial = template_habit.requires_evidence
                self.fields["enable_ai_proof_verification"].initial = template_habit.enable_ai_proof_verification

            if template_habit.validation_rule in [Habit.ValidationRule.TIME_WINDOW, Habit.ValidationRule.TIME_AND_EVIDENCE]:
                self.fields["window_start_time"].required = True
                self.fields["window_end_time"].required = True

            if template_habit.validation_rule == Habit.ValidationRule.NUMERIC_TARGET:
                self.fields["target_value"].required = True
                self.fields["unit_label"].required = True

    def clean(self):
        cleaned_data = super().clean()
        rule = getattr(self.template_habit, "validation_rule", None)

        if rule in [Habit.ValidationRule.TIME_WINDOW, Habit.ValidationRule.TIME_AND_EVIDENCE]:
            start = cleaned_data.get("window_start_time")
            end = cleaned_data.get("window_end_time")
            if not start:
                self.add_error("window_start_time", "Window start time is required.")
            if not end:
                self.add_error("window_end_time", "Window end time is required.")
            if start and end and start >= end:
                self.add_error("window_end_time", "Window end time must be later than start time.")

        if rule == Habit.ValidationRule.NUMERIC_TARGET:
            target = cleaned_data.get("target_value")
            unit = cleaned_data.get("unit_label")
            if target is None or target <= 0:
                self.add_error("target_value", "Target value must be greater than zero.")
            if not unit or not unit.strip():
                self.add_error("unit_label", "Unit label is required (e.g. liters, mins).")

        freq = cleaned_data.get("frequency")
        if freq == Habit.Frequency.WEEKLY_TARGET:
            if not cleaned_data.get("target_days_per_week"):
                cleaned_data["target_days_per_week"] = 3
        if freq == Habit.Frequency.WEEKDAYS:
            days = cleaned_data.get("selected_weekdays")
            if not days:
                self.add_error("selected_weekdays", "Please select at least one day for weekly frequency.")
            else:
                try:
                    cleaned_data["selected_weekdays"] = [int(d) for d in days]
                except (ValueError, TypeError):
                    self.add_error("selected_weekdays", "Invalid weekday selection.")
        else:
            cleaned_data["selected_weekdays"] = []

        if not cleaned_data.get("start_date"):
            cleaned_data["start_date"] = timezone.localdate()

        is_loc = cleaned_data.get("is_location_restricted", False)
        if is_loc:
            t_lat = cleaned_data.get("target_latitude")
            t_lng = cleaned_data.get("target_longitude")
            radius = cleaned_data.get("allowed_radius_meters")
            if t_lat is None:
                self.add_error("target_latitude", "Target latitude is required when location restriction is enabled.")
            elif not (-90.0 <= float(t_lat) <= 90.0):
                self.add_error("target_latitude", "Latitude must be between -90 and +90 degrees.")

            if t_lng is None:
                self.add_error("target_longitude", "Target longitude is required when location restriction is enabled.")
            elif not (-180.0 <= float(t_lng) <= 180.0):
                self.add_error("target_longitude", "Longitude must be between -180 and +180 degrees.")

            if radius is not None and int(radius) < 10:
                self.add_error("allowed_radius_meters", "Allowed radius must be at least 10 meters.")
            if not radius:
                cleaned_data["allowed_radius_meters"] = 150

        return cleaned_data
