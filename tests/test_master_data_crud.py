import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from habits.models import Habit, HabitCategory, RuleStrategy, seed_default_master_data_for_tenant
from tenants.models import Tenant, Membership

User = get_user_model()


class MasterDataCRUDTestCase(TestCase):
    def setUp(self):
        # Tenant A setup (Technical User with access to master data)
        self.user_a = User.objects.create_user(
            username="Alice",
            email="alice@example.com",
            password="password123",
            role=User.Role.TECHNICAL_USER,
        )
        self.tenant_a = Tenant.objects.create(name="Tenant A Workspace", slug="tenant-a")
        Membership.objects.create(
            user=self.user_a,
            tenant=self.tenant_a,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )

        # Tenant B setup (Technical User with access to master data)
        self.user_b = User.objects.create_user(
            username="Bob",
            email="bob@example.com",
            password="password123",
            role=User.Role.TECHNICAL_USER,
        )
        self.tenant_b = Tenant.objects.create(name="Tenant B Workspace", slug="tenant-b")
        Membership.objects.create(
            user=self.user_b,
            tenant=self.tenant_b,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE,
        )

        # Log in as user_a by default
        self.client.login(username="Alice", password="password123")

    def test_seed_default_master_data_for_tenant(self):
        """
        Verify seeding generates baseline 6 categories per tenant and 5 common rule strategies globally.
        """
        seed_default_master_data_for_tenant(self.tenant_a)
        self.assertEqual(HabitCategory.objects.filter(tenant=self.tenant_a).count(), 6)
        self.assertEqual(RuleStrategy.objects.count(), 5)

        # Idempotence: calling again shouldn't duplicate
        seed_default_master_data_for_tenant(self.tenant_a)
        self.assertEqual(HabitCategory.objects.filter(tenant=self.tenant_a).count(), 6)
        self.assertEqual(RuleStrategy.objects.count(), 5)

        # Seeding another tenant should NOT duplicate rule strategies (common for everyone)
        seed_default_master_data_for_tenant(self.tenant_b)
        self.assertEqual(HabitCategory.objects.filter(tenant=self.tenant_b).count(), 6)
        self.assertEqual(RuleStrategy.objects.count(), 5)

    def test_category_crud_workflow(self):
        """
        Test Create, Read, Update, Delete workflow for HabitCategory.
        """
        # 1. Create Category
        create_resp = self.client.post(reverse("category_create"), {
            "name": "Mindfulness and Meditation",
            "icon": "🧘",
            "color": "#10b981",
            "description": "Daily mental wellness routines.",
            "is_active": "on",
        })
        self.assertEqual(create_resp.status_code, 302)
        cat = HabitCategory.objects.filter(tenant=self.tenant_a, name="Mindfulness and Meditation").first()
        self.assertIsNotNone(cat)
        self.assertEqual(cat.icon, "🧘")
        self.assertEqual(cat.color, "#10b981")

        # 2. Read / List Category
        list_resp = self.client.get(reverse("category_list"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Mindfulness and Meditation")
        self.assertContains(list_resp, "🧘")

        # Search filter
        search_resp = self.client.get(reverse("category_list") + "?q=Mindfulness")
        self.assertContains(search_resp, "Mindfulness and Meditation")

        # 3. Update Category
        edit_resp = self.client.post(reverse("category_edit", kwargs={"pk": cat.pk}), {
            "name": "Mindfulness (Updated)",
            "icon": "🧠",
            "color": "#6366f1",
            "description": "Updated description",
            "is_active": "on",
        })
        self.assertEqual(edit_resp.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual(cat.name, "Mindfulness (Updated)")
        self.assertEqual(cat.icon, "🧠")

        # 4. Delete Category
        del_confirm_resp = self.client.get(reverse("category_delete", kwargs={"pk": cat.pk}))
        self.assertEqual(del_confirm_resp.status_code, 200)

        del_resp = self.client.post(reverse("category_delete", kwargs={"pk": cat.pk}))
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(HabitCategory.objects.filter(pk=cat.pk).exists())

    def test_rule_strategy_crud_workflow(self):
        """
        Test Create, Read, Update, Delete workflow for RuleStrategy.
        """
        # 1. Create Rule Strategy
        create_resp = self.client.post(reverse("rule_strategy_create"), {
            "name": "Evening Step Target",
            "engine_type": RuleStrategy.EngineType.NUMERIC_TARGET,
            "default_unit": "steps",
            "description": "Must log at least 10,000 steps daily.",
            "is_active": "on",
        })
        self.assertEqual(create_resp.status_code, 302)
        strat = RuleStrategy.objects.filter(name="Evening Step Target").first()
        self.assertIsNotNone(strat)
        self.assertEqual(strat.engine_type, RuleStrategy.EngineType.NUMERIC_TARGET)
        self.assertTrue(strat.requires_numeric)

        # 2. Read / List Rule Strategy
        list_resp = self.client.get(reverse("rule_strategy_list"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Evening Step Target")

        # 3. Update Rule Strategy
        edit_resp = self.client.post(reverse("rule_strategy_edit", kwargs={"pk": strat.pk}), {
            "name": "Daily Steps Target (Updated)",
            "engine_type": RuleStrategy.EngineType.NUMERIC_TARGET,
            "default_unit": "steps",
            "description": "Updated step goal.",
            "is_active": "on",
        })
        self.assertEqual(edit_resp.status_code, 302)
        strat.refresh_from_db()
        self.assertEqual(strat.name, "Daily Steps Target (Updated)")

        # 4. Delete Rule Strategy
        del_resp = self.client.post(reverse("rule_strategy_delete", kwargs={"pk": strat.pk}))
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(RuleStrategy.objects.filter(pk=strat.pk).exists())

    def test_tenant_isolation_on_master_data(self):
        """
        Verify categories are tenant-isolated, while rule strategies are common system-wide master data.
        Regular users cannot modify rule strategies; technical users manage common strategies.
        """
        cat_a = HabitCategory.objects.create(
            tenant=self.tenant_a,
            name="Confidential Category A",
        )
        strat = RuleStrategy.objects.create(
            name="Common Strategy X",
            engine_type=RuleStrategy.EngineType.STANDARD,
        )

        # Log in as user_b (Tenant B, Technical User)
        self.client.login(username="Bob", password="password123")

        # Category list view should not show Tenant A's category
        list_cat_resp = self.client.get(reverse("category_list"))
        self.assertNotContains(list_cat_resp, "Confidential Category A")

        # Rule strategy list view shows common strategy to authorized tech user
        list_strat_resp = self.client.get(reverse("rule_strategy_list"))
        self.assertContains(list_strat_resp, "Common Strategy X")

        # Category edit/delete by Tenant B must return 404
        self.assertEqual(self.client.get(reverse("category_edit", kwargs={"pk": cat_a.pk})).status_code, 404)
        self.assertEqual(self.client.post(reverse("category_delete", kwargs={"pk": cat_a.pk})).status_code, 404)

        # Regular user without permissions gets 403 on rule strategy management
        reg_user = User.objects.create_user(
            username="Charlie",
            email="charlie@example.com",
            password="password123",
            role=User.Role.REGULAR_USER,
        )
        self.client.login(username="Charlie", password="password123")
        self.assertEqual(self.client.get(reverse("rule_strategy_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("rule_strategy_create")).status_code, 403)

    def test_habit_creation_with_master_data_sync(self):
        """
        Verify creating a habit with category_ref and rule_strategy_ref syncs correctly.
        """
        cat = HabitCategory.objects.create(
            tenant=self.tenant_a,
            name="Deep Work",
            icon="⚡",
        )
        strat = RuleStrategy.objects.create(
            name="Focused Coding Hours",
            engine_type=RuleStrategy.EngineType.NUMERIC_TARGET,
            default_unit="hours",
        )

        create_resp = self.client.post(reverse("habit_create"), {
            "name": "Write 2 hrs Clean Code",
            "category_ref": cat.pk,
            "rule_strategy_ref": strat.pk,
            "frequency": Habit.Frequency.DAILY,
            "start_date": datetime.date.today().isoformat(),
            "target_value": "2.0",
            "unit_label": "hours",
            "is_active": "on",
        })
        self.assertEqual(create_resp.status_code, 302)

        habit = Habit.objects.filter(tenant=self.tenant_a, name="Write 2 hrs Clean Code").first()
        self.assertIsNotNone(habit)
        self.assertEqual(habit.category_ref, cat)
        self.assertEqual(habit.category, "Deep Work")
        self.assertEqual(habit.rule_strategy_ref, strat)
        self.assertEqual(habit.validation_rule, Habit.ValidationRule.NUMERIC_TARGET)
        self.assertEqual(habit.target_value, 2.0)

    def test_regular_user_cannot_access_master_data(self):
        """
        Regular users are restricted to their own dashboard and habits,
        and receive 403 Forbidden when attempting to access Category or Rule Strategy master data CRUD.
        """
        reg_user = User.objects.create_user(
            username="RegularRyan",
            email="ryan@example.com",
            password="password123",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            user=reg_user,
            tenant=self.tenant_a,
            role=Membership.Role.MEMBER,
            status=Membership.Status.ACTIVE,
        )
        self.client.login(username="RegularRyan", password="password123")

        # Category views return 403 Forbidden
        self.assertEqual(self.client.get(reverse("category_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("category_create")).status_code, 403)

        # Rule strategy views return 403 Forbidden
        self.assertEqual(self.client.get(reverse("rule_strategy_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("rule_strategy_create")).status_code, 403)
