from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class UserRegistrationForm(forms.ModelForm):
    """
    Form for registering a new user with automatic personal workspace provisioning.
    """
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Enter a strong password",
            "autocomplete": "new-password",
        }),
        help_text=password_validation.password_validators_help_text_html(),
    )
    password_confirm = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Re-enter your password",
            "autocomplete": "new-password",
        }),
    )

    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Choose a username",
                "autocomplete": "username",
            }),
            "email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm:
            if password != password_confirm:
                self.add_error("password_confirm", "Passwords do not match.")
            else:
                temp_user = User(
                    username=cleaned_data.get("username", ""),
                    email=cleaned_data.get("email", "")
                )
                try:
                    password_validation.validate_password(password, user=temp_user)
                except ValidationError as e:
                    self.add_error("password", e)

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            # Automatically create personal workspace and OWNER membership
            create_personal_workspace_for_user(user)
        return user


class UserLoginForm(forms.Form):
    """
    Form for authenticating using either username or email.
    """
    username = forms.CharField(
        label="Username or Email",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter username or email",
            "autocomplete": "username",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your password",
            "autocomplete": "current-password",
        }),
    )


class AdminUserCreateForm(forms.ModelForm):
    """
    Form for administrators to create new users from the Admin Panel.
    """
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Enter user password",
        }),
    )
    role = forms.ChoiceField(
        choices=User.Role.choices,
        required=False,
        initial=User.Role.REGULAR_USER,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    workspace_name = forms.CharField(
        label="Workspace / Organization Name",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "e.g., My Company, Personal Workspace",
        }),
        help_text="Optional. Defaults to '<username>'s Personal Workspace'.",
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "username"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "user@example.com"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
        }

    def clean_role(self):
        role = self.cleaned_data.get("role")
        if not role:
            if self.data.get("is_staff") in ["on", True, "true", "1"]:
                return User.Role.SUPER_ADMIN
            return User.Role.REGULAR_USER
        return role

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data.get("role") or User.Role.REGULAR_USER
        if user.role == User.Role.SUPER_ADMIN:
            user.is_superuser = True
            user.is_staff = True
        else:
            user.is_superuser = False
            user.is_staff = False
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            ws_name = self.cleaned_data.get("workspace_name")
            create_personal_workspace_for_user(user, workspace_name=ws_name)
        return user


class AdminUserEditForm(forms.ModelForm):
    """
    Form for administrators to edit an existing user's profile, role,
    workspace name, and optionally reset their password.
    """
    role = forms.ChoiceField(
        choices=User.Role.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    is_staff = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        label="Staff Status (Legacy)",
    )
    new_password = forms.CharField(
        label="Reset Password",
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Leave blank to keep existing password",
            "autocomplete": "new-password",
        }),
        help_text="Leave blank unless you wish to change this user's password.",
    )
    workspace_name = forms.CharField(
        label="Primary Workspace Name",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Workspace name",
        }),
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role", "is_active"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            membership = self.instance.memberships.select_related("tenant").filter(status="ACTIVE").first()
            if membership and membership.tenant:
                self.initial["workspace_name"] = membership.tenant.name
            self.initial["role"] = self.instance.role

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        is_staff = self.data.get("is_staff") in ["on", True, "true", "1"]
        if not role:
            if is_staff:
                cleaned_data["role"] = User.Role.SUPER_ADMIN
            else:
                cleaned_data["role"] = getattr(self.instance, "role", User.Role.REGULAR_USER)
        elif is_staff and "role" not in self.data:
            cleaned_data["role"] = User.Role.SUPER_ADMIN
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data.get("role") or user.role
        if user.role == User.Role.SUPER_ADMIN:
            user.is_superuser = True
            user.is_staff = True
        else:
            user.is_superuser = False
            user.is_staff = False

        new_password = self.cleaned_data.get("new_password")
        if new_password:
            user.set_password(new_password)

        if commit:
            user.save()
            new_ws_name = self.cleaned_data.get("workspace_name")
            if new_ws_name:
                membership = user.memberships.select_related("tenant").filter(status="ACTIVE").first()
                if membership and membership.tenant:
                    membership.tenant.name = new_ws_name
                    membership.tenant.save(update_fields=["name", "updated_at"])
        return user
