import os
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from accounts.services import (
    INITIAL_ADMIN_PROFILES,
    are_admin_accounts_seeded,
    create_bootstrap_admin,
    seed_admin_accounts,
)
from db_manager.services import (
    PROTECTED_DATABASES,
    drop_database,
    list_databases,
    verify_master_password,
)
from tenants.models import Tenant

User = get_user_model()


class BootstrapAdminAndSelfDestructTest(TestCase):
    """
    Tests for temporary bootstrap admin ('admin' / 'admin') creation
    and automatic self-destruction upon 'Add Admin Data' completion.
    """

    def setUp(self):
        Tenant.objects.all().delete()
        User.objects.all().delete()

    def test_create_bootstrap_admin(self):
        admin = create_bootstrap_admin()
        self.assertEqual(admin.username, "admin")
        self.assertEqual(admin.role, User.Role.SUPER_ADMIN)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.check_password("admin"))
        self.assertFalse(admin.must_reset_password)

        # Idempotency check: calling again returns same user
        admin_repeat = create_bootstrap_admin()
        self.assertEqual(admin.id, admin_repeat.id)
        self.assertEqual(User.objects.filter(username="admin").count(), 1)

    def test_seed_admin_accounts_deletes_bootstrap_admin(self):
        # 1. Create bootstrap admin
        bootstrap_admin = create_bootstrap_admin()
        self.assertTrue(User.objects.filter(username="admin").exists())

        # 2. Run seed_admin_accounts
        result = seed_admin_accounts(
            common_password="SecretPass123!",
            executing_user=bootstrap_admin,
        )

        self.assertTrue(result["bootstrap_deleted"])
        # Bootstrap admin MUST be deleted from database
        self.assertFalse(User.objects.filter(username="admin").exists())

        # Permanent admin accounts must exist
        shrinath = User.objects.get(username="Shrinath_jayakumar")
        self.assertTrue(shrinath.check_password("SecretPass123!"))
        self.assertEqual(shrinath.role, User.Role.SUPER_ADMIN)

        akash = User.objects.get(username="Akash_ps")
        self.assertTrue(akash.check_password("SecretPass123!"))
        self.assertEqual(akash.role, User.Role.TECHNICAL_USER)

        romy = User.objects.get(username="Romy_fred")
        self.assertTrue(romy.check_password("SecretPass123!"))
        self.assertEqual(romy.role, User.Role.REGULAR_USER)

        self.assertTrue(are_admin_accounts_seeded())

    def test_seed_admin_accounts_preserves_executing_super_admin(self):
        # If Shrinath_jayakumar already exists and runs the provisioning,
        # their personal password and session flags must not be clobbered.
        shrinath = User.objects.create(
            username="Shrinath_jayakumar",
            email="shrinath_jayakumar@gmail.com",
            role=User.Role.SUPER_ADMIN,
            is_superuser=True,
            is_staff=True,
            must_reset_password=False,
        )
        shrinath.set_password("ShrinathPersonalPass@2026")
        shrinath.save()

        result = seed_admin_accounts(
            common_password="NewTeamPassword99!",
            executing_user=shrinath,
        )

        shrinath.refresh_from_db()
        # Password remains personal, must_reset_password remains False
        self.assertTrue(shrinath.check_password("ShrinathPersonalPass@2026"))
        self.assertFalse(shrinath.must_reset_password)

        # Team accounts have the new common password and must reset
        akash = User.objects.get(username="Akash_ps")
        self.assertTrue(akash.check_password("NewTeamPassword99!"))
        self.assertTrue(akash.must_reset_password)

    def test_admin_seed_data_view_logs_out_bootstrap_admin(self):
        # Simulates bootstrap admin logging in, triggering Add Admin Data in UI
        admin = create_bootstrap_admin()
        client = Client()
        client.force_login(admin)

        response = client.post(
            reverse("admin_seed_data"),
            {"common_password": "InitialPass123!"},
            follow=True,
        )

        # Should redirect to login after self-destruction
        self.assertRedirects(response, reverse("login"))
        self.assertFalse(User.objects.filter(username="admin").exists())
        self.assertTrue(User.objects.filter(username="Shrinath_jayakumar").exists())


class DatabaseManagerServiceAndViewsTest(TestCase):
    """
    Tests for Odoo-style Database Manager (/db-manager/).
    """

    def setUp(self):
        self.client = Client()

    def test_master_password_verification(self):
        self.assertTrue(verify_master_password("admin"))
        self.assertFalse(verify_master_password("wrong_password"))
        self.assertFalse(verify_master_password(""))

    def test_protected_databases_cannot_be_dropped(self):
        for protected_db in PROTECTED_DATABASES:
            with self.assertRaises(ValueError):
                drop_database(protected_db)

    def test_auth_view_access(self):
        # Unauthenticated access to /db-manager/ shows auth form
        res = self.client.get(reverse("db_manager_index"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Master Password")

        # Wrong password fails
        post_res = self.client.post(reverse("db_manager_auth"), {"master_password": "wrong"})
        self.assertEqual(post_res.status_code, 200)
        self.assertContains(post_res, "Invalid Master Password")

        # Correct password redirects and unlocks dashboard
        post_ok = self.client.post(reverse("db_manager_auth"), {"master_password": "admin"}, follow=True)
        self.assertEqual(post_ok.status_code, 200)
        self.assertContains(post_ok, "Available PostgreSQL Databases")

    def test_drop_protected_database_via_post_blocked(self):
        # Authenticate session via auth endpoint
        self.client.post(reverse("db_manager_auth"), {"master_password": "admin"})

        res = self.client.post(
            reverse("db_manager_drop"),
            {"db_name": "habit_tracker", "confirm_master_password": "admin"},
            follow=True,
        )
        self.assertContains(res, "Protected database &#x27;habit_tracker&#x27; cannot be dropped")
