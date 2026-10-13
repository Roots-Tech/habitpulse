from django.contrib import admin
from .models import Habit, HabitCompletion


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "category", "frequency", "start_date", "is_active", "created_at"]
    list_filter = ["tenant", "category", "frequency", "is_active"]
    search_fields = ["name", "description", "tenant__name"]


@admin.register(HabitCompletion)
class HabitCompletionAdmin(admin.ModelAdmin):
    list_display = ["habit", "tenant", "completion_date", "created_at"]
    list_filter = ["tenant", "completion_date"]
    search_fields = ["habit__name", "tenant__name"]
