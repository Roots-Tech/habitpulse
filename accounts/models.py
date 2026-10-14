from django.contrib.auth.models import AbstractUser
from django.db import models


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
