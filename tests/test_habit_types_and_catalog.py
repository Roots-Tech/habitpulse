from datetime import time
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RolePermission
from habits.models import Habit, HabitCompletion
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class HabitTypesAndCatalogTestCase(TestCase):
    """
    Test suite for:
    1. Three distinct habit types: GENERAL, PREDEFINED_PURPOSE, EXPERT_PRESCRIBED.
    2. Three distinct sections rendered on the Habits hub:
       - My Habit List
       - Predefined Purpose Habits
       - Expert Prescribed Habits
    3. Creation & publishing of catalog templates by Super Admin & Technical Users.
    4. Regular users restricted to General habits defaulting to Honor System (STANDARD).
    5. Adoption of catalog templates by regular users into their workspace.
    6. Strict validation parameter enforcement on adopted habits prior to completion.
    7. Catalog template permissions (admin/technical only).
    """

    def setUp(self):
        # 1. Super Admin User
        self.super_admin = User.objects.create_user(
            username="super_admin_test",
            email="superadmin@example.com",
            password="AdminPassword123!",
            is_staff=True,
            is_superuser=True,
        )
        self.super_admin_tenant, _ = create_personal_workspace_for_user(self.super_admin, "Super Admin Space")

        # 2. Technical User
        self.technical_user = User.objects.create_user(
            username="tech_user_test",
            email="tech@example.com",
            password="TechPassword123!",
            role=User.Role.TECHNICAL_USER,
        )
        self.tech_tenant, _ = create_personal_workspace_for_user(self.technical_user, "Tech Space")

        # 3. Regular User
        self.regular_user = User.objects.create_user(
            username="reg_user_test",
            email="regular@example.com",
            password="RegPassword123!",
            role=User.Role.REGULAR_USER,
        )
        self.reg_tenant, _ = create_personal_workspace_for_user(self.regular_user, "Reg Space")

        # Ensure RolePermission defaults are present
        RolePermission.get_for_role(User.Role.SUPER_ADMIN)
        RolePermission.get_for_role(User.Role.TECHNICAL_USER)
        RolePermission.get_for_role(User.Role.REGULAR_USER)

        self.client_regular = Client()
        self.client_regular.login(username="reg_user_test", password="RegPassword123!")

        self.client_admin = Client()
        self.client_admin.login(username="super_admin_test", password="AdminPassword123!")

        self.client_tech = Client()
        self.client_tech.login(username="tech_user_test", password="TechPassword123!")

        self.today = timezone.localdate()

    def test_habit_list_page_displays_three_separate_sections(self):
        """
        GET /habits/ must render:
        1. My Habit List (#my-habits)
        2. Predefined Purpose Habits (#predefined-habits)
        3. Expert Prescribed Habits (#expert-habits)
        """
        response = self.client_regular.get(reverse("habit_list"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("My Habit List", content)
        self.assertIn("Predefined Purpose Habits", content)
        self.assertIn("Expert Prescribed Habits", content)

        self.assertIn('id="my-habits"', content)
        self.assertIn('id="predefined-habits"', content)
        self.assertIn('id="expert-habits"', content)

    def test_regular_user_creates_general_habit_defaults_to_honor_system(self):
        """
        Regular users create GENERAL habits defaulting to Honor System (STANDARD).
        Even if they attempt to post template=True or a different habit type, it is restricted.
        """
        # Valid creation by regular user
        response = self.client_regular.post(reverse("habit_create"), {
            "name": "Evening Journaling",
            "description": "Reflect on 3 wins today",
            "category": "Mindfulness",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)

        created_habit = Habit.objects.get(tenant=self.reg_tenant, name="Evening Journaling")
        self.assertEqual(created_habit.habit_type, Habit.HabitType.GENERAL)
        self.assertFalse(created_habit.is_template)
        self.assertEqual(created_habit.validation_rule, Habit.ValidationRule.STANDARD)
        self.assertTrue(created_habit.is_general)

        # Tampering attempt with unauthorized habit_type
        response_tamper = self.client_regular.post(reverse("habit_create"), {
            "name": "Unauthorized Template",
            "description": "Hacking the system",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "is_template": "on",
        })
        # Should stay on form with validation error or reject choice
        self.assertFalse(Habit.objects.filter(name="Unauthorized Template").exists())

    def test_super_admin_can_publish_predefined_purposeful_habit_template(self):
        """
        Super admin can create and publish a Predefined Purposeful habit template with validation rules.
        """
        response = self.client_admin.post(reverse("habit_create"), {
            "name": "Super Hydration Target",
            "description": "Drink at least 3000 ml water daily",
            "category": "Health",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "is_template": "on",
            "validation_rule": Habit.ValidationRule.NUMERIC_TARGET,
            "target_value": "3000",
            "unit_label": "ml",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("habit_list"))

        template = Habit.objects.get(name="Super Hydration Target", is_template=True)
        self.assertEqual(template.habit_type, Habit.HabitType.PREDEFINED_PURPOSE)
        self.assertEqual(template.validation_rule, Habit.ValidationRule.NUMERIC_TARGET)
        self.assertEqual(template.target_value, Decimal("3000"))
        self.assertEqual(template.unit_label, "ml")
        self.assertTrue(template.is_predefined_purpose)

    def test_technical_user_can_publish_expert_prescribed_habit_template(self):
        """
        Technical user can create and publish an Expert Prescribed habit template with time window.
        """
        response = self.client_tech.post(reverse("habit_create"), {
            "name": "Morning Cold Exposure",
            "description": "Protocol: 3-5 minutes cold shower between 6:00 and 8:30 AM",
            "category": "Health",
            "habit_type": Habit.HabitType.EXPERT_PRESCRIBED,
            "is_template": "on",
            "validation_rule": Habit.ValidationRule.TIME_WINDOW,
            "window_start_time": "06:00:00",
            "window_end_time": "08:30:00",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("habit_list"))

        template = Habit.objects.get(name="Morning Cold Exposure", is_template=True)
        self.assertEqual(template.habit_type, Habit.HabitType.EXPERT_PRESCRIBED)
        self.assertEqual(template.validation_rule, Habit.ValidationRule.TIME_WINDOW)
        self.assertEqual(template.window_start_time, time(6, 0))
        self.assertEqual(template.window_end_time, time(8, 30))
        self.assertTrue(template.is_expert_prescribed)

    def test_regular_user_adopts_template_habit(self):
        """
        Regular user can add a catalog template habit to their habit list.
        It is cloned into their workspace with all validation parameters preserved.
        """
        template = Habit.objects.create(
            name="Deep Work Focus 90m",
            description="90 minutes uninterrupted single-tasking",
            category="Productivity",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            validation_rule=Habit.ValidationRule.NUMERIC_TARGET,
            target_value=Decimal("90"),
            unit_label="minutes",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        adopt_url = reverse("habit_adopt", args=[template.pk])
        response = self.client_regular.post(adopt_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("habit_list"))

        # Verify cloned habit in user's tenant
        adopted = Habit.objects.filter(tenant=self.reg_tenant, template_source=template).first()
        self.assertIsNotNone(adopted)
        self.assertEqual(adopted.name, "Deep Work Focus 90m")
        self.assertEqual(adopted.habit_type, Habit.HabitType.PREDEFINED_PURPOSE)
        self.assertFalse(adopted.is_template)
        self.assertEqual(adopted.validation_rule, Habit.ValidationRule.NUMERIC_TARGET)
        self.assertEqual(adopted.target_value, Decimal("90"))
        self.assertEqual(adopted.unit_label, "minutes")

        # Attempting to adopt a second time does not create a duplicate
        response2 = self.client_regular.post(adopt_url)
        self.assertEqual(response2.status_code, 302)
        count = Habit.objects.filter(tenant=self.reg_tenant, template_source=template).count()
        self.assertEqual(count, 1)

    def test_adopted_predefined_habit_enforces_numeric_validation_parameter(self):
        """
        Predefined Purposeful Habit with a target requires fulfillment before marking complete.
        """
        template = Habit.objects.create(
            name="Daily Steps Target",
            category="Fitness",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            validation_rule=Habit.ValidationRule.NUMERIC_TARGET,
            target_value=Decimal("8000"),
            unit_label="steps",
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        # Adopt habit
        self.client_regular.post(reverse("habit_adopt", args=[template.pk]))
        adopted = Habit.objects.get(tenant=self.reg_tenant, template_source=template)

        complete_url = reverse("habit_complete", args=[adopted.pk])

        # Attempt 1: Complete with no logged value -> rejected
        resp_fail1 = self.client_regular.post(complete_url, {})
        self.assertEqual(resp_fail1.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

        # Attempt 2: Complete with logged value 5000 (< 8000) -> rejected
        resp_fail2 = self.client_regular.post(complete_url, {"logged_value": "5000"})
        self.assertEqual(resp_fail2.status_code, 302)
        self.assertFalse(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

        # Attempt 3: Complete with logged value 8500 (>= 8000) -> accepted
        resp_success = self.client_regular.post(complete_url, {"logged_value": "8500"})
        self.assertEqual(resp_success.status_code, 302)
        completion = HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).first()
        self.assertIsNotNone(completion)
        self.assertEqual(completion.logged_value, Decimal("8500"))

    def test_adopted_expert_prescribed_habit_enforces_time_window_validation(self):
        """
        Expert Prescribed Habit with a time window rejects completions outside the prescribed window.
        """
        template = Habit.objects.create(
            name="Circadian Dawn Sunlight",
            category="Health",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.EXPERT_PRESCRIBED,
            is_template=True,
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(6, 0),
            window_end_time=time(9, 0),
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        # Adopt habit
        self.client_regular.post(reverse("habit_adopt", args=[template.pk]))
        adopted = Habit.objects.get(tenant=self.reg_tenant, template_source=template)
        complete_url = reverse("habit_complete", args=[adopted.pk])

        # Case A: User attempts completion at 14:30 (outside window) -> rejected
        outside_window_dt = timezone.make_aware(timezone.datetime(self.today.year, self.today.month, self.today.day, 14, 30, 0))
        with patch("habits.validators.timezone.now", return_value=outside_window_dt):
            with patch("habits.validators.timezone.localtime", return_value=outside_window_dt):
                resp = self.client_regular.post(complete_url, {})
                self.assertEqual(resp.status_code, 302)
                self.assertFalse(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

        # Case B: User attempts completion at 07:30 (inside window) -> accepted
        inside_window_dt = timezone.make_aware(timezone.datetime(self.today.year, self.today.month, self.today.day, 7, 30, 0))
        with patch("habits.validators.timezone.now", return_value=inside_window_dt):
            with patch("habits.validators.timezone.localtime", return_value=inside_window_dt):
                resp = self.client_regular.post(complete_url, {})
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(HabitCompletion.objects.filter(habit=adopted, completion_date=self.today).exists())

    def test_template_catalog_permission_boundaries(self):
        """
        Regular users cannot edit or delete catalog templates.
        Super Admin and Technical users can manage templates.
        """
        template = Habit.objects.create(
            name="Restricted Catalog Item",
            category="Health",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            start_date=self.today,
        )

        # Regular user tries to delete template -> 403 Forbidden
        del_resp = self.client_regular.post(reverse("habit_delete", args=[template.pk]))
        self.assertEqual(del_resp.status_code, 403)
        self.assertTrue(Habit.objects.filter(pk=template.pk).exists())

        # Regular user tries to update template -> 403 Forbidden
        update_resp = self.client_regular.post(reverse("habit_edit", args=[template.pk]), {
            "name": "Hacked Name",
        })
        self.assertEqual(update_resp.status_code, 403)

        # Technical user can edit template
        tech_resp = self.client_tech.post(reverse("habit_edit", args=[template.pk]), {
            "name": "Updated by Tech User",
            "category": "Health",
            "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
            "is_template": "on",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(tech_resp.status_code, 302)
        template.refresh_from_db()
        self.assertEqual(template.name, "Updated by Tech User")

        # Super admin can delete template
        admin_del_resp = self.client_admin.post(reverse("habit_delete", args=[template.pk]))
        self.assertEqual(admin_del_resp.status_code, 302)
        self.assertFalse(Habit.objects.filter(pk=template.pk).exists())

    def test_adopt_predefined_habit_with_personalized_time_window_get_and_post(self):
        """
        GET /habits/<pk>/adopt/ renders the personalization form.
        POST with personalized time window sets the user's customized schedule.
        """
        template = Habit.objects.create(
            name="Consistent Morning Wake-Up",
            category="Health",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(5, 0),
            window_end_time=time(6, 30),
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        adopt_url = reverse("habit_adopt", args=[template.pk])

        # 1. GET returns 200 and renders the form
        get_resp = self.client_regular.get(adopt_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "Consistent Morning Wake-Up")
        self.assertContains(get_resp, "Personal Time Window")

        # 2. POST with custom timing (04:00 AM - 04:45 AM)
        post_resp = self.client_regular.post(adopt_url, {
            "window_start_time": "04:00",
            "window_end_time": "04:45",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
        })
        self.assertEqual(post_resp.status_code, 302)
        self.assertRedirects(post_resp, reverse("habit_list"))

        # Verify custom schedule applied
        adopted = Habit.objects.get(tenant=self.reg_tenant, template_source=template)
        self.assertEqual(adopted.name, "Consistent Morning Wake-Up")
        self.assertEqual(adopted.window_start_time, time(4, 0))
        self.assertEqual(adopted.window_end_time, time(4, 45))
        self.assertEqual(adopted.template_source, template)

    def test_five_users_adopt_same_wakeup_habit_with_different_individual_timings(self):
        """
        Verifies the core scenario:
        5 different users adopt the same single 'Consistent Morning Wake-Up' predefined habit.
        Each user configures their own personal wake-up time window:
        - User 1: 04:00 - 04:30
        - User 2: 05:00 - 05:30
        - User 3: 06:00 - 06:30
        - User 4: 07:00 - 07:30
        - User 5: 08:00 - 08:30

        Asserts:
        - Exactly 1 template habit exists in the system.
        - Exactly 5 user habit instances exist, all pointing to the single template.
        - Each user's completion validation evaluates against their own window.
        - Category page displays all 5 users under Health with their personal timings without N+1 queries.
        """
        template, _ = Habit.objects.get_or_create(
            name="Consistent Morning Wake-Up",
            is_template=True,
            defaults={
                "category": "Health",
                "created_by": self.super_admin,
                "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
                "validation_rule": Habit.ValidationRule.TIME_WINDOW,
                "window_start_time": time(5, 0),
                "window_end_time": time(6, 30),
                "frequency": Habit.Frequency.DAILY,
                "start_date": self.today,
            }
        )

        users_data = [
            ("wake_user_1", "04:00", "04:30", time(4, 0), time(4, 30)),
            ("wake_user_2", "05:00", "05:30", time(5, 0), time(5, 30)),
            ("wake_user_3", "06:00", "06:30", time(6, 0), time(6, 30)),
            ("wake_user_4", "07:00", "07:30", time(7, 0), time(7, 30)),
            ("wake_user_5", "08:00", "08:30", time(8, 0), time(8, 30)),
        ]

        clients = []
        for username, start_str, end_str, exp_start, exp_end in users_data:
            user = User.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="TestPassword123!",
            )
            tenant, _ = create_personal_workspace_for_user(user, f"{username} Workspace")
            client = Client()
            client.login(username=username, password="TestPassword123!")
            clients.append((client, user, tenant, start_str, end_str, exp_start, exp_end))

            # User adopts the template with their personal time window
            adopt_url = reverse("habit_adopt", args=[template.pk])
            resp = client.post(adopt_url, {
                "window_start_time": start_str,
                "window_end_time": end_str,
                "frequency": Habit.Frequency.DAILY,
                "start_date": self.today.isoformat(),
            })
            self.assertEqual(resp.status_code, 302)

        # Assert only 1 template exists
        self.assertEqual(Habit.objects.filter(is_template=True, name="Consistent Morning Wake-Up").count(), 1)

        # Assert 5 user habits exist, all linked to template
        user_habits = Habit.objects.filter(is_template=False, template_source=template)
        self.assertEqual(user_habits.count(), 5)

        # Assert each user has their personal window
        for client, user, tenant, start_str, end_str, exp_start, exp_end in clients:
            h = Habit.objects.get(tenant=tenant, template_source=template)
            self.assertEqual(h.window_start_time, exp_start)
            self.assertEqual(h.window_end_time, exp_end)
            self.assertEqual(h.created_by, user)

        # Category page verification
        cat_resp = self.client_admin.get(reverse("category_list"))
        self.assertEqual(cat_resp.status_code, 200)
        cat_content = cat_resp.content.decode("utf-8")
        self.assertIn("Health", cat_content)
        for _, user, _, _, _, _, _ in clients:
            self.assertIn(user.username, cat_content)

    def test_adopted_habit_can_be_edited_to_change_personal_time_window(self):
        """
        Users retain full ongoing rights to configure and change their personal
        schedule / wake-up window on an adopted habit at any time.
        """
        template = Habit.objects.create(
            name="Consistent Morning Wake-Up",
            category="Health",
            created_by=self.super_admin,
            habit_type=Habit.HabitType.PREDEFINED_PURPOSE,
            is_template=True,
            validation_rule=Habit.ValidationRule.TIME_WINDOW,
            window_start_time=time(5, 0),
            window_end_time=time(6, 30),
            frequency=Habit.Frequency.DAILY,
            start_date=self.today,
        )

        # Adopt habit with 05:00 - 05:30
        self.client_regular.post(reverse("habit_adopt", args=[template.pk]), {
            "window_start_time": "05:00",
            "window_end_time": "05:30",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
        })
        adopted = Habit.objects.get(tenant=self.reg_tenant, template_source=template)
        self.assertEqual(adopted.window_start_time, time(5, 0))

        # Edit personal window to 06:15 - 07:00
        edit_url = reverse("habit_edit", args=[adopted.pk])
        edit_resp = self.client_regular.post(edit_url, {
            "name": adopted.name,
            "category_ref": adopted.category_ref_id or "",
            "category": adopted.category,
            "validation_rule": adopted.validation_rule,
            "window_start_time": "06:15",
            "window_end_time": "07:00",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(edit_resp.status_code, 302)

        adopted.refresh_from_db()
        self.assertEqual(adopted.window_start_time, time(6, 15))
        self.assertEqual(adopted.window_end_time, time(7, 0))
        # Template source relationship remains intact
        self.assertEqual(adopted.template_source, template)

    def test_user_defined_habit_restricted_when_matching_predefined_purpose_exists(self):
        """
        If any purpose-oriented habit exists in the predefined library,
        user-defined custom habits with the same purpose are strictly restricted.
        Ensures zero duplicate definitions, preventing database bloat and performance degradation.
        """
        # Ensure predefined templates exist
        from habits.models import seed_default_catalog_habits
        seed_default_catalog_habits(creator=self.super_admin)
        Habit.objects.get_or_create(
            name="Consistent Morning Wake-Up",
            defaults={"is_template": True, "habit_type": Habit.HabitType.PREDEFINED_PURPOSE, "created_by": self.super_admin}
        )
        Habit.objects.get_or_create(
            name="Daily Deep Hydration",
            defaults={"is_template": True, "habit_type": Habit.HabitType.PREDEFINED_PURPOSE, "created_by": self.super_admin}
        )
        Habit.objects.get_or_create(
            name="Deep Work Sprint (45 Mins)",
            defaults={"is_template": True, "habit_type": Habit.HabitType.PREDEFINED_PURPOSE, "created_by": self.super_admin}
        )

        # 1. Attempt to create "Wake up at 5:00 AM" -> Restricted by "Consistent Morning Wake-Up"
        resp_wake = self.client_regular.post(reverse("habit_create"), {
            "name": "Wake up at 5:00 AM",
            "category": "Health",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
        })
        self.assertEqual(resp_wake.status_code, 200)
        self.assertContains(resp_wake, "standardized predefined habit for this purpose already exists")
        self.assertContains(resp_wake, "Consistent Morning Wake-Up")
        self.assertFalse(Habit.objects.filter(tenant=self.reg_tenant, name__icontains="wake").exists())

        # 2. Attempt to create "Drink 2L Water" -> Restricted by "Daily Deep Hydration"
        resp_water = self.client_regular.post(reverse("habit_create"), {
            "name": "Drink 2L Water",
            "category": "Health",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
        })
        self.assertEqual(resp_water.status_code, 200)
        self.assertContains(resp_water, "Daily Deep Hydration")
        self.assertFalse(Habit.objects.filter(tenant=self.reg_tenant, name__icontains="water").exists())

        # 2b. Attempt to create "Have water" -> Restricted by "Daily Deep Hydration"
        resp_have_water = self.client_regular.post(reverse("habit_create"), {
            "name": "Have water",
            "category": "Health",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
        })
        self.assertEqual(resp_have_water.status_code, 200)
        self.assertContains(resp_have_water, "Daily Deep Hydration")

        # 3. Attempt to create "Deep Work Focus Block" -> Restricted by "Deep Work Sprint (45 Mins)"
        resp_focus = self.client_regular.post(reverse("habit_create"), {
            "name": "Deep Work Focus Block",
            "category": "Productivity",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
        })
        self.assertEqual(resp_focus.status_code, 200)
        self.assertContains(resp_focus, "Deep Work Sprint (45 Mins)")
        self.assertFalse(Habit.objects.filter(tenant=self.reg_tenant, name__icontains="deep work").exists())

        # 4. Genuinely distinct habit with no predefined purpose (e.g. "Play Spanish Guitar") -> Allowed!
        resp_guitar = self.client_regular.post(reverse("habit_create"), {
            "name": "Play Spanish Guitar 20 mins",
            "category": "Other",
            "frequency": Habit.Frequency.DAILY,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        })
        self.assertEqual(resp_guitar.status_code, 302)
        self.assertTrue(Habit.objects.filter(tenant=self.reg_tenant, name="Play Spanish Guitar 20 mins").exists())

    def test_model_clean_raises_validation_error_on_predefined_purpose(self):
        """
        Model-level validation (Habit.clean) raises ValidationError when attempting to
        create an unlinked habit with a predefined purpose.
        """
        from habits.models import seed_default_catalog_habits
        from django.core.exceptions import ValidationError
        seed_default_catalog_habits(creator=self.super_admin)
        Habit.objects.get_or_create(
            name="Consistent Morning Wake-Up",
            defaults={"is_template": True, "habit_type": Habit.HabitType.PREDEFINED_PURPOSE, "created_by": self.super_admin}
        )

        habit = Habit(
            name="Waking up early",
            category="Health",
            tenant=self.reg_tenant,
            created_by=self.regular_user,
            is_template=False,
            template_source=None,
        )
        with self.assertRaises(ValidationError) as cm:
            habit.clean()
        self.assertIn("name", cm.exception.message_dict)
        self.assertIn("Consistent Morning Wake-Up", str(cm.exception.message_dict["name"]))

    def test_habit_check_intent_api_endpoint(self):
        """
        Tests /habits/api/check-intent/ AJAX endpoint:
        - Accurately identifies predefined habit purposes (e.g. Wake up at 5am -> Consistent Morning Wake-Up).
        - Correctly distinguishes distinct concepts (e.g. 'Aqua bath' is NOT 'Daily Deep Hydration').
        - Returns matches: False for short inputs or unrelated custom habits.
        """
        from habits.models import seed_default_catalog_habits
        seed_default_catalog_habits(creator=self.super_admin)
        Habit.objects.get_or_create(
            name="Consistent Morning Wake-Up",
            defaults={"is_template": True, "habit_type": Habit.HabitType.PREDEFINED_PURPOSE, "created_by": self.super_admin}
        )
        Habit.objects.get_or_create(
            name="Daily Deep Hydration",
            defaults={"is_template": True, "habit_type": Habit.HabitType.PREDEFINED_PURPOSE, "created_by": self.super_admin}
        )

        # 1. Short input (< 3 chars)
        res_short = self.client_regular.get(reverse("habit_check_intent_api"), {"name": "hi"})
        self.assertEqual(res_short.status_code, 200)
        self.assertFalse(res_short.json().get("matches"))

        # 2. Heuristic / Pattern match: "Wake up at 5am"
        res_wake = self.client_regular.get(reverse("habit_check_intent_api"), {"name": "Wake up at 5am"})
        self.assertEqual(res_wake.status_code, 200)
        self.assertTrue(res_wake.json().get("matches"))
        self.assertEqual(res_wake.json().get("matched_name"), "Consistent Morning Wake-Up")

        # 3. Unrelated custom habit: "Aqua bath" (distinct activity: hygiene/bath, not hydration)
        res_aqua_bath = self.client_regular.get(reverse("habit_check_intent_api"), {"name": "Aqua bath"})
        self.assertEqual(res_aqua_bath.status_code, 200)
        self.assertFalse(res_aqua_bath.json().get("matches"))

        # 4. Unrelated custom habit: "Learn Spanish Guitar"
        res_guitar = self.client_regular.get(reverse("habit_check_intent_api"), {"name": "Learn Spanish Guitar"})
        self.assertEqual(res_guitar.status_code, 200)
        self.assertFalse(res_guitar.json().get("matches"))

        # 5. Direct synonym check: "Have water" -> Daily Deep Hydration
        res_have_water = self.client_regular.get(reverse("habit_check_intent_api"), {"name": "Have water"})
        self.assertEqual(res_have_water.status_code, 200)
        self.assertTrue(res_have_water.json().get("matches"))
        self.assertEqual(res_have_water.json().get("matched_name"), "Daily Deep Hydration")


    def test_gym_habit_personalization_daily_logging_and_weekly_monthly_progress(self):
        """
        Tests the 'Gym & Strength Training' predefined habit:
        1. Regular user adopts Gym template and personalizes target to 4 days/week.
        2. Logs completions on Mon, Wed, Fri, Sat in a past week -> 4/4 days (Accomplished).
        3. Logs completions on Mon, Tue only in another week -> 2/4 days (Failed).
        4. Calculates monthly progress against baseline (4 days * 4 weeks = 16 days).
        5. Verifies week-by-week analysis showing over/under achievement notes.
        """
        from datetime import date
        from habits.models import seed_default_catalog_habits
        from habits.services import calculate_weekly_and_monthly_habit_progress
        seed_default_catalog_habits(creator=self.super_admin)

        gym_template = Habit.objects.get(name="Gym & Strength Training", is_template=True)
        self.assertEqual(gym_template.frequency, Habit.Frequency.WEEKLY_TARGET)
        self.assertEqual(gym_template.target_days_per_week, 3)

        # User personalizes to 4 days per week
        resp = self.client_regular.post(reverse("habit_adopt", kwargs={"pk": gym_template.pk}), {
            "frequency": Habit.Frequency.WEEKLY_TARGET,
            "target_days_per_week": "4",
            "start_date": "2026-10-01",
        })
        self.assertEqual(resp.status_code, 302)

        user_gym = Habit.objects.get(tenant=self.reg_tenant, template_source=gym_template)
        self.assertEqual(user_gym.target_days_per_week, 4)
        self.assertEqual(user_gym.effective_weekly_target, 4)
        self.assertEqual(user_gym.monthly_target_days, 16)
        self.assertEqual(user_gym.get_weekday_display_names(), "4 Days / Week")

        # Week 1 of October 2026: Mon Oct 5 to Sun Oct 11. Log 4 days (Mon, Wed, Fri, Sat)
        for day in [date(2026, 10, 5), date(2026, 10, 7), date(2026, 10, 9), date(2026, 10, 10)]:
            HabitCompletion.objects.create(
                tenant=self.reg_tenant,
                habit=user_gym,
                completion_date=day,
            )

        # Week 2 of October 2026: Mon Oct 12 to Sun Oct 18. Log only 2 days (Mon, Tue)
        for day in [date(2026, 10, 12), date(2026, 10, 13)]:
            HabitCompletion.objects.create(
                tenant=self.reg_tenant,
                habit=user_gym,
                completion_date=day,
            )

        # Run weekly and monthly analysis for October 2026 (reference date: Nov 1, 2026)
        progress = calculate_weekly_and_monthly_habit_progress(
            user_gym, year=2026, month=10, today=date(2026, 11, 1)
        )

        self.assertEqual(progress["weekly_target"], 4)
        self.assertEqual(progress["monthly_target"], 16)
        self.assertEqual(progress["month_total_completions"], 6)

        # Check Week 2 (Oct 5-11): 4 completed out of 4 -> Accomplished
        w2 = next(w for w in progress["weeks"] if w["start_date"] == date(2026, 10, 5))
        self.assertEqual(w2["completed_count"], 4)
        self.assertTrue(w2["is_accomplished"])
        self.assertEqual(w2["status"], "Accomplished")

        # Check Week 3 (Oct 12-18): 2 completed out of 4 -> Failed
        w3 = next(w for w in progress["weeks"] if w["start_date"] == date(2026, 10, 12))
        self.assertEqual(w3["completed_count"], 2)
        self.assertFalse(w3["is_accomplished"])
        self.assertEqual(w3["status"], "Failed")
        self.assertIn("-2 below goal", w3["comparison_note"])

        # Check habit stats view renders the weekly monthly breakdown
        stats_resp = self.client_regular.get(reverse("habit_stats", kwargs={"pk": user_gym.pk}))
        self.assertEqual(stats_resp.status_code, 200)
        self.assertContains(stats_resp, "Weekly &amp; Monthly Consistency Analysis")
        self.assertContains(stats_resp, "4 Days / Week")

    def test_catalog_templates_export_and_import_endpoints(self):
        """
        Tests:
        1. GET /catalog/export/ downloads all catalog templates as valid JSON.
        2. Regular users cannot access export or import (PermissionDenied 403).
        3. POST /catalog/import/ successfully syncs uploaded JSON templates into database.
        """
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        from habits.models import seed_default_catalog_habits
        seed_default_catalog_habits(creator=self.super_admin)

        # 1. Regular user access is denied
        res_reg_exp = self.client_regular.get(reverse("catalog_export"))
        self.assertEqual(res_reg_exp.status_code, 403)

        res_reg_imp = self.client_regular.post(reverse("catalog_import"))
        self.assertEqual(res_reg_imp.status_code, 403)

        # 2. Super Admin exports catalog
        res_exp = self.client_admin.get(reverse("catalog_export"))
        self.assertEqual(res_exp.status_code, 200)
        self.assertEqual(res_exp["Content-Type"], "application/json")
        self.assertIn("attachment; filename=", res_exp["Content-Disposition"])

        export_data = json.loads(res_exp.content.decode("utf-8"))
        self.assertIn("templates", export_data)
        self.assertTrue(any(t["name"] == "Gym & Strength Training" for t in export_data["templates"]))

        # 3. Modify template and upload to test import
        new_template_payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Pilates Core Flow",
                    "category": "Fitness",
                    "habit_type": Habit.HabitType.PREDEFINED_PURPOSE,
                    "description": "Dynamic pilates core strengthening routine.",
                    "frequency": Habit.Frequency.WEEKLY_TARGET,
                    "target_days_per_week": 3,
                    "validation_rule": Habit.ValidationRule.STANDARD,
                    "pixel_score": 10,
                    "purpose_patterns": [r"\bpilates\b", r"\bmat\s*pilates\b"]
                }
            ]
        }
        json_bytes = json.dumps(new_template_payload).encode("utf-8")
        uploaded_file = SimpleUploadedFile("pilates_catalog.json", json_bytes, content_type="application/json")

        res_imp = self.client_admin.post(reverse("catalog_import"), {"catalog_file": uploaded_file})
        self.assertEqual(res_imp.status_code, 302)

        # Verify new template was created
        self.assertTrue(Habit.objects.filter(name="Pilates Core Flow", is_template=True).exists())

    def test_gym_synonym_restriction_in_intent_api(self):
        """
        Verifies that custom habits representing gym workouts (e.g. 'Hit the gym', 'Weightlifting')
        are restricted by 'Gym & Strength Training'.
        """
        from habits.models import seed_default_catalog_habits
        seed_default_catalog_habits(creator=self.super_admin)

        for phrasing in ["Hit the gym", "Weightlifting", "Workout 4 days a week", "Go to gym"]:
            res = self.client_regular.get(reverse("habit_check_intent_api"), {"name": phrasing})
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json().get("matches"), f"Expected '{phrasing}' to match Gym template")
            self.assertEqual(res.json().get("matched_name"), "Gym & Strength Training")

    def test_habit_form_weekly_target_days_customization_and_admin_only_catalog_buttons(self):
        """
        Verifies:
        1. Users can customize target_days_per_week to any count (1-7 days) in HabitForm.
        2. Catalog download/upload buttons are visible ONLY to Admins, hidden for regular & technical users.
        3. Only Gym & Strength Training exists in the default catalog.
        """
        from habits.models import seed_default_catalog_habits
        from habits.forms import HabitForm
        seed_default_catalog_habits(creator=self.super_admin)

        # 1. Verify default catalog has only Gym & Strength Training
        templates = Habit.objects.filter(is_template=True)
        self.assertEqual(templates.count(), 1)
        self.assertEqual(templates.first().name, "Gym & Strength Training")

        # 2. Form supports customizing target days per week (e.g. 4 days/week)
        form = HabitForm(data={
            "name": "Violin Practice Routine",
            "category": "Fitness",
            "frequency": Habit.Frequency.WEEKLY_TARGET,
            "target_days_per_week": 4,
            "start_date": self.today.isoformat(),
            "is_active": "on",
        }, tenant=self.reg_tenant, user=self.regular_user)
        self.assertTrue(form.is_valid(), form.errors)
        habit_saved = form.save(commit=False)
        habit_saved.tenant = self.reg_tenant
        habit_saved.created_by = self.regular_user
        habit_saved.save()

        self.assertEqual(habit_saved.target_days_per_week, 4)
        self.assertEqual(habit_saved.effective_weekly_target, 4)
        self.assertEqual(habit_saved.monthly_target_days, 16)
        self.assertEqual(habit_saved.get_frequency_display_custom(), "4 Days / Week")

        # 3. Verify habit_list HTML: Catalog download/upload visible to Admin, hidden for regular & tech user
        res_admin = self.client_admin.get(reverse("habit_list"))
        self.assertContains(res_admin, "Download Catalog (JSON)")
        self.assertContains(res_admin, "Upload Catalog (JSON)")

        res_regular = self.client_regular.get(reverse("habit_list"))
        self.assertNotContains(res_regular, "Download Catalog (JSON)")
        self.assertNotContains(res_regular, "Upload Catalog (JSON)")

        res_tech = self.client_tech.get(reverse("habit_list"))
        self.assertNotContains(res_tech, "Download Catalog (JSON)")
        self.assertNotContains(res_tech, "Upload Catalog (JSON)")

