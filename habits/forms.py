import uuid
from django import forms
from django.utils import timezone
from .models import Habit, HabitCategory, HabitCompletion, RuleStrategy
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

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if not self.tenant and self.instance and self.instance.pk and hasattr(self.instance, "tenant"):
            self.tenant = self.instance.tenant

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Category name cannot be empty.")
        if self.tenant:
            qs = HabitCategory.objects.filter(tenant=self.tenant, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"A habit category named '{name}' already exists in your workspace.")
        return name


class RuleStrategyForm(forms.ModelForm):
    """
    Form for creating and editing Master Data Rule Strategies.
    Strictly tenant-scoped.
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

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if not self.tenant and self.instance and self.instance.pk and hasattr(self.instance, "tenant"):
            self.tenant = self.instance.tenant

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Rule strategy name cannot be empty.")
        if self.tenant:
            qs = RuleStrategy.objects.filter(tenant=self.tenant, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"A rule strategy named '{name}' already exists in your workspace.")
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
            "selected_weekdays",
            "start_date",
            "is_active",
            "validation_rule",
            "window_start_time",
            "window_end_time",
            "target_value",
            "unit_label",
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

        is_admin_or_tech = bool(self.user and (self.user.is_super_admin or self.user.is_technical_user))

        # Determine effective habit type for defaults
        current_type = (
            habit_type_initial
            or (self.instance.habit_type if self.instance and self.instance.pk else None)
            or self.initial.get("habit_type")
            or Habit.HabitType.GENERAL
        )

        # Set initial pixel_score
        if self.instance and self.instance.pk and self.instance.pixel_score:
            self.initial["pixel_score"] = self.instance.pixel_score
        elif "pixel_score" not in self.initial:
            if current_type == Habit.HabitType.EXPERT_PRESCRIBED:
                self.initial["pixel_score"] = 10
            elif current_type == Habit.HabitType.PREDEFINED_PURPOSE:
                self.initial["pixel_score"] = 5
            else:
                self.initial["pixel_score"] = 2

        if not is_admin_or_tech:
            # Standard users can only create General habits with fixed 2 pixels
            self.fields["habit_type"].choices = [
                (Habit.HabitType.GENERAL, "General Habit (Honor System)"),
            ]
            self.fields["habit_type"].initial = Habit.HabitType.GENERAL
            self.fields["is_template"].initial = False
            self.fields["is_template"].widget = forms.HiddenInput()
            self.fields["pixel_score"].initial = 2
            self.fields["pixel_score"].widget = forms.HiddenInput()
        else:
            if habit_type_initial:
                self.initial["habit_type"] = habit_type_initial
            if is_template_initial is not None:
                self.initial["is_template"] = is_template_initial
            elif habit_type_initial in [Habit.HabitType.PREDEFINED_PURPOSE, Habit.HabitType.EXPERT_PRESCRIBED]:
                self.initial["is_template"] = True

        if self.tenant:
            self.fields["category_ref"].queryset = HabitCategory.objects.filter(
                tenant=self.tenant, is_active=True
            )
            self.fields["rule_strategy_ref"].queryset = RuleStrategy.objects.filter(
                tenant=self.tenant, is_active=True
            )
        else:
            self.fields["category_ref"].queryset = HabitCategory.objects.filter(is_active=True)
            self.fields["rule_strategy_ref"].queryset = RuleStrategy.objects.filter(is_active=True)

        if not self.instance.pk:
            if not self.initial.get("rule_strategy_ref") and self.tenant:
                default_strat = RuleStrategy.objects.filter(
                    tenant=self.tenant, engine_type=RuleStrategy.EngineType.STANDARD
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

            is_template = bool(self.cleaned_data.get("is_template") or self.initial.get("is_template"))
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
        elif cleaned_data.get("category") and self.tenant:
            cat, _ = HabitCategory.objects.get_or_create(
                tenant=self.tenant,
                name=cleaned_data.get("category"),
                defaults={"is_active": True},
            )
            cleaned_data["category_ref"] = cat
            cleaned_data["category"] = cat.name

        # 2. Resolve Rule Strategy
        rule_strategy_ref = cleaned_data.get("rule_strategy_ref")
        habit_type = cleaned_data.get("habit_type") or Habit.HabitType.GENERAL
        is_admin_or_tech = bool(self.user and (self.user.is_super_admin or self.user.is_technical_user))
        if not is_admin_or_tech:
            cleaned_data["habit_type"] = Habit.HabitType.GENERAL
            cleaned_data["is_template"] = False
        else:
            cleaned_data["habit_type"] = habit_type
            cleaned_data["is_template"] = bool(cleaned_data.get("is_template", False))

        if rule_strategy_ref:
            rule = rule_strategy_ref.engine_type
            cleaned_data["validation_rule"] = rule
        else:
            rule = cleaned_data.get("validation_rule") or Habit.ValidationRule.STANDARD
            cleaned_data["validation_rule"] = rule
            if self.tenant:
                strat = RuleStrategy.objects.filter(tenant=self.tenant, engine_type=rule).first()
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

        # 3. Pixel Score Validation & Enforcement
        if habit_type == Habit.HabitType.GENERAL or not is_admin_or_tech:
            cleaned_data["pixel_score"] = 2
            self.instance.pixel_score = 2
        else:
            score = cleaned_data.get("pixel_score")
            if score is None or score == "":
                default_score = 10 if habit_type == Habit.HabitType.EXPERT_PRESCRIBED else 5
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
        habit.habit_type = self.cleaned_data.get("habit_type") or habit.habit_type or Habit.HabitType.GENERAL
        habit.is_template = bool(self.cleaned_data.get("is_template", False))
        habit.pixel_score = self.cleaned_data.get("pixel_score", 2)
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
