from django.urls import path
from . import views

urlpatterns = [
    path("onboarding/", views.onboarding_view, name="onboarding"),
    path("habits/", views.habit_list_view, name="habit_list"),
    path("habits/create/", views.habit_create_view, name="habit_create"),
    path("habits/<int:pk>/edit/", views.habit_update_view, name="habit_edit"),
    path("habits/<int:pk>/adopt/", views.habit_adopt_view, name="habit_adopt"),
    path("habits/<int:pk>/delete/", views.habit_delete_view, name="habit_delete"),
    path("habits/<int:pk>/toggle-active/", views.habit_toggle_active_view, name="habit_toggle_active"),
    path("habits/<int:pk>/complete/", views.habit_complete_view, name="habit_complete"),
    path("habits/<int:pk>/undo/", views.habit_undo_complete_view, name="habit_undo_complete"),
    path("habits/<int:pk>/calendar/", views.habit_calendar_view, name="habit_calendar"),
    path("habits/<int:pk>/stats/", views.habit_stats_view, name="habit_stats"),

    # Master Data - Habit Categories (Full CRUD)
    path("categories/", views.category_list_view, name="category_list"),
    path("categories/create/", views.category_create_view, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_update_view, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete_view, name="category_delete"),

    # Master Data - Rule Strategies (Full CRUD)
    path("rule-strategies/", views.rule_strategy_list_view, name="rule_strategy_list"),
    path("rule-strategies/create/", views.rule_strategy_create_view, name="rule_strategy_create"),
    path("rule-strategies/<int:pk>/edit/", views.rule_strategy_update_view, name="rule_strategy_edit"),
    path("rule-strategies/<int:pk>/delete/", views.rule_strategy_delete_view, name="rule_strategy_delete"),
]
