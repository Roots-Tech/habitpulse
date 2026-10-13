from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from habits.models import Habit, HabitCompletion
from tenants.models import Membership, Tenant
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds demo users, personal workspaces, sample habits, and history for testing."

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        # 1. Demo User
        username = "demo"
        email = "demo@example.com"
        password = "Password123!"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email},
        )
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        # 2. Admin Superuser
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@gmail.com"},
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.set_password("Password123!")
        admin_user.save()

        # 3. Promote any existing registered users to staff & superuser
        for u in User.objects.all():
            u.is_staff = True
            u.is_superuser = True
            u.save()

        # Find or create personal workspace
        membership = Membership.objects.filter(user=user).first()
        if not membership:
            tenant, _ = create_personal_workspace_for_user(user, "Demo's Personal Workspace")
        else:
            tenant = membership.tenant

        today = timezone.localdate()

        # Clear existing demo habits
        Habit.objects.filter(tenant=tenant).delete()

        # Habit 1: Daily Python Practice (started 14 days ago, high streak)
        h1 = Habit.objects.create(
            tenant=tenant,
            created_by=user,
            name="Practice Python Coding",
            description="Spend 30 minutes solving coding problems and reading docs",
            category=Habit.Category.LEARNING,
            frequency=Habit.Frequency.DAILY,
            selected_weekdays=[0, 1, 2, 3, 4, 5, 6],
            start_date=today - timedelta(days=14),
            is_active=True,
        )
        # Complete last 7 days consecutively up to yesterday
        for i in range(1, 8):
            HabitCompletion.objects.create(
                tenant=tenant,
                habit=h1,
                completion_date=today - timedelta(days=i),
            )

        # Habit 2: Exercise for 30 minutes (Weekdays only: Mon-Fri)
        h2 = Habit.objects.create(
            tenant=tenant,
            created_by=user,
            name="Exercise for 30 minutes",
            description="Cardio, gym, or brisk walking",
            category=Habit.Category.FITNESS,
            frequency=Habit.Frequency.WEEKDAYS,
            selected_weekdays=[0, 1, 2, 3, 4],  # Mon-Fri
            start_date=today - timedelta(days=21),
            is_active=True,
        )
        # Add completions for past eligible weekdays
        for i in range(1, 15):
            d = today - timedelta(days=i)
            if d.weekday() in [0, 1, 2, 3, 4] and i % 3 != 0:
                HabitCompletion.objects.create(
                    tenant=tenant,
                    habit=h2,
                    completion_date=d,
                )

        # Habit 3: Drink 2 Liters Water
        h3 = Habit.objects.create(
            tenant=tenant,
            created_by=user,
            name="Drink Enough Water",
            description="Reach daily hydration goal",
            category=Habit.Category.HEALTH,
            frequency=Habit.Frequency.DAILY,
            selected_weekdays=[0, 1, 2, 3, 4, 5, 6],
            start_date=today - timedelta(days=10),
            is_active=True,
        )
        for i in range(2, 6):
            HabitCompletion.objects.create(
                tenant=tenant,
                habit=h3,
                completion_date=today - timedelta(days=i),
            )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded demo data!\n"
            f"Username: {username}\n"
            f"Email: {email}\n"
            f"Password: {password}\n"
            f"Workspace: {tenant.name}"
        ))
