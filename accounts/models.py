from django.contrib.auth.models import AbstractUser
from django.db import models


PERMISSIONS_DEFINITIONS = [
    {
        "key": "view_dashboard",
        "label": "Frontend Application & Dashboard",
        "description": "View main dashboard, streak counters, and completion analytics.",
        "menu": "Dashboard",
        "default_super": True,
        "default_technical": True,
        "default_regular": True,
    },
    {
        "key": "manage_habits",
        "label": "Create, View & Track Personal Habits",
        "description": "Create, edit, toggle, track, and complete personal habits.",
        "menu": "Habits, + New Habit",
        "default_super": True,
        "default_technical": True,
        "default_regular": True,
    },
    {
        "key": "manage_categories",
        "label": "Master Data Management (Habit Categories)",
        "description": "Full CRUD access to create, view, edit, and delete habit categories.",
        "menu": "Categories",
        "default_super": True,
        "default_technical": True,
        "default_regular": False,
    },
    {
        "key": "manage_rule_strategies",
        "label": "Master Data Management (Rule Strategies)",
        "description": "Full CRUD access to create, view, edit, and delete rule strategies.",
        "menu": "Rule Strategies",
        "default_super": True,
        "default_technical": True,
        "default_regular": False,
    },
    {
        "key": "manage_users",
        "label": "Admin Panel (Users Management)",
        "description": "Provision, edit, activate/deactivate users, and reset user passwords.",
        "menu": "Admin Panel ▾ > Users",
        "default_super": True,
        "default_technical": False,
        "default_regular": False,
    },
    {
        "key": "manage_roles",
        "label": "Admin Panel (User Roles & Access Control)",
        "description": "Configure role permissions, reassign user roles, and customize access.",
        "menu": "Admin Panel ▾ > User Roles",
        "default_super": True,
        "default_technical": False,
        "default_regular": False,
    },
    {
        "key": "access_django_admin",
        "label": "Django Admin & Database Operations (/admin/)",
        "description": "Access raw database tables and underlying Django administration.",
        "menu": "Admin Panel ▾ > Django Admin",
        "default_super": True,
        "default_technical": False,
        "default_regular": False,
    },
]


class User(AbstractUser):
    """
    Custom user model for the application.
    Enforces unique email addresses and supports access-based user roles:
    1. SUPER_ADMIN: Unrestricted access to frontend, backend, database admin, user management, passwords.
    2. TECHNICAL_USER: Developer/technical access to all application features, habits, and master data; restricted from admin panel/db.
    3. REGULAR_USER: Access strictly limited to their own dashboard and personal habits.
    """
    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        TECHNICAL_USER = "TECHNICAL_USER", "Technical User"
        REGULAR_USER = "REGULAR_USER", "Regular User"

    email = models.EmailField(
        unique=True,
        error_messages={
            "unique": "A user with that email already exists.",
        },
    )
    must_reset_password = models.BooleanField(
        default=False,
        help_text="Flags if the user must reset their password on first login.",
    )
    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.REGULAR_USER,
        help_text="Designated system access role",
    )

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser

    @property
    def is_technical_user(self):
        return self.role == self.Role.TECHNICAL_USER and not self.is_superuser

    @property
    def is_regular_user(self):
        return self.role == self.Role.REGULAR_USER and not self.is_superuser and self.role != self.Role.TECHNICAL_USER

    def get_role_badge(self):
        if self.is_super_admin:
            return {
                "label": "Super Admin",
                "class": "badge-super-admin",
                "icon": "👑",
                "color": "#c084fc",
                "bg": "rgba(168, 85, 247, 0.15)",
                "border": "rgba(168, 85, 247, 0.4)",
            }
        elif self.is_technical_user:
            return {
                "label": "Technical User",
                "class": "badge-technical-user",
                "icon": "🛠️",
                "color": "#38bdf8",
                "bg": "rgba(56, 189, 248, 0.15)",
                "border": "rgba(56, 189, 248, 0.4)",
            }
        return {
            "label": "Regular User",
            "class": "badge-regular-user",
            "icon": "👤",
            "color": "#34d399",
            "bg": "rgba(16, 185, 129, 0.15)",
            "border": "rgba(16, 185, 129, 0.4)",
        }

    def has_perm_access(self, perm_key):
        """
        Evaluates whether user has access to a specific functional capability,
        checking user-level custom overrides first, then falling back to role-level permissions.
        Super Admin always retains all permissions with zero database query overhead.
        """
        if self.is_superuser or self.role == self.Role.SUPER_ADMIN:
            return True

        # Check user-level custom override
        try:
            override = UserPermissionOverride.objects.filter(user_id=self.id).first()
            if override and override.enable_custom:
                return getattr(override, perm_key, False)
        except Exception:
            pass

        # Fallback to role-level configurable permissions
        try:
            role_perm = RolePermission.get_for_role(self.role)
            return getattr(role_perm, perm_key, False)
        except Exception:
            if self.role == self.Role.TECHNICAL_USER:
                return perm_key in ["view_dashboard", "manage_habits", "manage_categories", "manage_rule_strategies"]
            return perm_key in ["view_dashboard", "manage_habits"]

    @property
    def can_view_dashboard(self):
        return self.has_perm_access("view_dashboard")

    @property
    def can_manage_habits(self):
        return self.has_perm_access("manage_habits")

    @property
    def can_manage_categories(self):
        return self.has_perm_access("manage_categories")

    @property
    def can_manage_rule_strategies(self):
        return self.has_perm_access("manage_rule_strategies")

    @property
    def can_manage_users(self):
        return self.has_perm_access("manage_users")

    @property
    def can_manage_roles(self):
        return self.has_perm_access("manage_roles")

    @property
    def can_access_django_admin(self):
        return self.has_perm_access("access_django_admin")

    @property
    def can_access_admin_panel(self):
        return self.can_manage_users or self.can_manage_roles or self.can_access_django_admin

    def save(self, *args, **kwargs):
        # Synchronize Django's built-in permission flags with the designated system role
        if self.role == self.Role.SUPER_ADMIN:
            self.is_superuser = True
            self.is_staff = True
        elif self.role in [self.Role.TECHNICAL_USER, self.Role.REGULAR_USER]:
            # If a new user is created with is_superuser or is_staff without specifying a custom role,
            # upgrade them to SUPER_ADMIN
            if self._state.adding and (self.is_superuser or self.is_staff) and self.role == self.Role.REGULAR_USER:
                self.role = self.Role.SUPER_ADMIN
                self.is_superuser = True
                self.is_staff = True
            else:
                self.is_superuser = False
                self.is_staff = False
        elif self.is_superuser or self.is_staff:
            self.role = self.Role.SUPER_ADMIN
            self.is_superuser = True
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class RolePermission(models.Model):
    """
    Configurable permissions for each system role (SUPER_ADMIN, TECHNICAL_USER, REGULAR_USER).
    Can be dynamically modified by Super Admins via checkboxes.
    """
    role = models.CharField(max_length=30, unique=True, choices=User.Role.choices)
    view_dashboard = models.BooleanField(default=True)
    manage_habits = models.BooleanField(default=True)
    manage_categories = models.BooleanField(default=False)
    manage_rule_strategies = models.BooleanField(default=False)
    manage_users = models.BooleanField(default=False)
    manage_roles = models.BooleanField(default=False)
    access_django_admin = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_for_role(cls, role_code):
        defaults = {
            User.Role.SUPER_ADMIN: {
                "view_dashboard": True,
                "manage_habits": True,
                "manage_categories": True,
                "manage_rule_strategies": True,
                "manage_users": True,
                "manage_roles": True,
                "access_django_admin": True,
            },
            User.Role.TECHNICAL_USER: {
                "view_dashboard": True,
                "manage_habits": True,
                "manage_categories": True,
                "manage_rule_strategies": True,
                "manage_users": False,
                "manage_roles": False,
                "access_django_admin": False,
            },
            User.Role.REGULAR_USER: {
                "view_dashboard": True,
                "manage_habits": True,
                "manage_categories": False,
                "manage_rule_strategies": False,
                "manage_users": False,
                "manage_roles": False,
                "access_django_admin": False,
            },
        }
        role_defaults = defaults.get(role_code, defaults[User.Role.REGULAR_USER])
        obj, _ = cls.objects.get_or_create(role=role_code, defaults=role_defaults)
        return obj

    def to_dict(self):
        return {
            "view_dashboard": self.view_dashboard,
            "manage_habits": self.manage_habits,
            "manage_categories": self.manage_categories,
            "manage_rule_strategies": self.manage_rule_strategies,
            "manage_users": self.manage_users,
            "manage_roles": self.manage_roles,
            "access_django_admin": self.access_django_admin,
        }

    def __str__(self):
        return f"Permissions for {self.get_role_display()}"


class UserPermissionOverride(models.Model):
    """
    Granular user-level custom permission overrides.
    Allows Super Admins to provide any specific user access to any page or menu as needed.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="permission_override")
    enable_custom = models.BooleanField(default=False, help_text="Enable custom permissions overriding role defaults")
    view_dashboard = models.BooleanField(default=True)
    manage_habits = models.BooleanField(default=True)
    manage_categories = models.BooleanField(default=False)
    manage_rule_strategies = models.BooleanField(default=False)
    manage_users = models.BooleanField(default=False)
    manage_roles = models.BooleanField(default=False)
    access_django_admin = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def to_dict(self):
        return {
            "view_dashboard": self.view_dashboard,
            "manage_habits": self.manage_habits,
            "manage_categories": self.manage_categories,
            "manage_rule_strategies": self.manage_rule_strategies,
            "manage_users": self.manage_users,
            "manage_roles": self.manage_roles,
            "access_django_admin": self.access_django_admin,
        }

    def __str__(self):
        status = "Active" if self.enable_custom else "Inactive"
        return f"Custom Override for {self.user.username} ({status})"
