from django import forms
from django.utils import timezone
from .models import Habit, HabitCompletion
from .validators import HabitCompletionValidationEngine


class HabitForm(forms.ModelForm):
    """
    Form for creating and editing habits.
    Validates name, frequency, selected weekdays, start date, and validation rules.
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

    class Meta:
        model = Habit
        fields = [
            "name",
            "description",
            "category",
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
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional details or motivation...",
            }),
            "category": forms.Select(attrs={"class": "form-control"}),
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected_weekdays"].required = False
        self.fields["validation_rule"].required = False
        self.fields["window_start_time"].required = False
        self.fields["window_end_time"].required = False
        self.fields["target_value"].required = False
        self.fields["unit_label"].required = False

        if not self.instance.pk and not self.initial.get("validation_rule"):
            self.initial["validation_rule"] = Habit.ValidationRule.STANDARD

        if not self.instance.pk and not self.initial.get("start_date"):
            self.initial["start_date"] = timezone.localdate()
            self.initial["is_active"] = True

        if self.instance.pk and self.instance.selected_weekdays:
            self.initial["weekdays"] = [str(d) for d in self.instance.selected_weekdays]

    def clean(self):
        cleaned_data = super().clean()
        frequency = cleaned_data.get("frequency")
        weekdays = cleaned_data.get("weekdays") or []
        rule = cleaned_data.get("validation_rule") or Habit.ValidationRule.STANDARD
        cleaned_data["validation_rule"] = rule
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

        return cleaned_data

    def save(self, commit=True):
        habit = super().save(commit=False)
        habit.selected_weekdays = self.cleaned_data.get("selected_weekdays", [])
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
