from django.urls import path
from . import views

urlpatterns = [
    path("onboarding/", views.onboarding_view, name="onboarding"),
    path("habits/", views.habit_list_view, name="habit_list"),
    path("habits/create/", views.habit_create_view, name="habit_create"),
    path("habits/<int:pk>/edit/", views.habit_update_view, name="habit_edit"),
    path("habits/<int:pk>/toggle-active/", views.habit_toggle_active_view, name="habit_toggle_active"),
    path("habits/<int:pk>/complete/", views.habit_complete_view, name="habit_complete"),
    path("habits/<int:pk>/undo/", views.habit_undo_complete_view, name="habit_undo_complete"),
    path("habits/<int:pk>/calendar/", views.habit_calendar_view, name="habit_calendar"),
    path("habits/<int:pk>/stats/", views.habit_stats_view, name="habit_stats"),
]
