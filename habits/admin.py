from django.contrib import admin
from .models import Habit, HabitCategory, HabitCompletion, RuleStrategy


@admin.register(HabitCategory)
class HabitCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "color", "tenant", "is_active", "created_at"]
    list_filter = ["tenant", "is_active"]
    search_fields = ["name", "description", "tenant__name"]


@admin.register(RuleStrategy)
class RuleStrategyAdmin(admin.ModelAdmin):
    list_display = ["name", "engine_type", "default_unit", "is_active", "created_at"]
    list_filter = ["engine_type", "is_active"]
    search_fields = ["name", "description"]


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "category", "validation_rule", "frequency", "start_date", "is_active", "created_at"]
    list_filter = ["tenant", "category", "validation_rule", "frequency", "is_active"]
    search_fields = ["name", "description", "tenant__name"]


@admin.register(HabitCompletion)
class HabitCompletionAdmin(admin.ModelAdmin):
    list_display = ["habit", "tenant", "completion_date", "created_at"]
    list_filter = ["tenant", "completion_date"]
    search_fields = ["habit__name", "tenant__name"]
