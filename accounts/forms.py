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


from accounts.models import PERMISSIONS_DEFINITIONS, UserPermissionOverride

class AdminUserEditForm(forms.ModelForm):
    """
    Form for administrators to edit an existing user's profile, role,
    workspace name, permissions, and optionally reset their password.
    Non-superadmin users can view their own profile and access capabilities
    in read-only mode, without the ability to modify permissions or roles.
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
    enable_custom_permissions = forms.BooleanField(
        required=False,
        label="Enable Custom Permission Overrides",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "enable_custom_permissions"}),
        help_text="Override system role defaults and set custom capabilities for this specific user.",
    )
    # Individual system capability checkboxes
    perm_view_dashboard = forms.BooleanField(
        required=False,
        label="Frontend Application & Dashboard",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
    )
    perm_manage_habits = forms.BooleanField(
        required=False,
        label="Create, View & Track Personal Habits",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
    )
    perm_manage_categories = forms.BooleanField(
        required=False,
        label="Master Data Management (Habit Categories)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
    )
    perm_manage_rule_strategies = forms.BooleanField(
        required=False,
        label="Master Data Management (Rule Strategies)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
    )
    perm_manage_users = forms.BooleanField(
        required=False,
        label="Admin Panel (Users Management)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
    )
    perm_manage_roles = forms.BooleanField(
        required=False,
        label="Admin Panel (User Roles & Access Control)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
    )
    perm_access_django_admin = forms.BooleanField(
        required=False,
        label="Django Admin & Database Operations (/admin/)",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
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

    def __init__(self, *args, is_super_admin=True, **kwargs):
        self.is_super_admin = is_super_admin
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            membership = self.instance.memberships.select_related("tenant").filter(status="ACTIVE").first()
            if membership and membership.tenant:
                self.initial["workspace_name"] = membership.tenant.name
            self.initial["role"] = self.instance.role

            override = getattr(self.instance, "permission_override", None)
            if override and override.enable_custom:
                self.initial["enable_custom_permissions"] = True
                for defn in PERMISSIONS_DEFINITIONS:
                    self.initial[f"perm_{defn['key']}"] = getattr(override, defn["key"], False)
            else:
                self.initial["enable_custom_permissions"] = False
                for defn in PERMISSIONS_DEFINITIONS:
                    self.initial[f"perm_{defn['key']}"] = self.instance.has_perm_access(defn["key"])

        # If requesting user is NOT a super admin, lock role, username, is_active, and all permissions
        if not self.is_super_admin:
            for field_name in [
                "username", "role", "is_active", "enable_custom_permissions",
                "perm_view_dashboard", "perm_manage_habits", "perm_manage_categories",
                "perm_manage_rule_strategies", "perm_manage_users", "perm_manage_roles",
                "perm_access_django_admin"
            ]:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if self.is_super_admin:
            role = cleaned_data.get("role")
            is_staff = self.data.get("is_staff") in ["on", True, "true", "1"]
            if not role:
                if is_staff:
                    cleaned_data["role"] = User.Role.SUPER_ADMIN
                else:
                    cleaned_data["role"] = getattr(self.instance, "role", User.Role.REGULAR_USER)
            elif is_staff and "role" not in self.data:
                cleaned_data["role"] = User.Role.SUPER_ADMIN
        else:
            # Retain original role for non-superadmin users
            cleaned_data["role"] = getattr(self.instance, "role", User.Role.REGULAR_USER)
            cleaned_data["is_active"] = getattr(self.instance, "is_active", True)
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        if self.is_super_admin:
            user.role = self.cleaned_data.get("role") or user.role
            if user.role == User.Role.SUPER_ADMIN:
                user.is_superuser = True
                user.is_staff = True
            else:
                user.is_superuser = False
                user.is_staff = False
        else:
            user.role = self.instance.role
            user.is_superuser = self.instance.is_superuser
            user.is_staff = self.instance.is_staff
            user.is_active = self.instance.is_active

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

            if self.is_super_admin:
                override, _ = UserPermissionOverride.objects.get_or_create(user=user)
                enable_custom = bool(self.cleaned_data.get("enable_custom_permissions"))
                override.enable_custom = enable_custom
                for defn in PERMISSIONS_DEFINITIONS:
                    key = defn["key"]
                    field_val = bool(self.cleaned_data.get(f"perm_{key}"))
                    setattr(override, key, field_val)
                override.save()

        return user
