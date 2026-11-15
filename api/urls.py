from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    path("dashboard/", views.dashboard_api, name="dashboard"),
    path("habits/<int:pk>/complete/", views.habit_complete_api, name="habit_complete"),
    path("habits/<int:pk>/undo/", views.habit_undo_api, name="habit_undo"),
    path("habits/<int:pk>/status/", views.habit_status_api, name="habit_status"),
    path("users/", views.users_list_api, name="users_list"),
    path("admin/performance/", views.admin_performance_api, name="admin_performance"),
    path("admin/performance/reset/", views.admin_performance_reset_api, name="admin_performance_reset"),
    path("resolve-map-url/", views.resolve_map_url_api, name="resolve_map_url"),
    path("habits/<int:pk>/reminder/", views.habit_reminder_api, name="habit_reminder"),
    path("habits/<int:pk>/reminder/snooze/", views.habit_reminder_snooze_api, name="habit_reminder_snooze"),
    path("habits/reminders/active/", views.active_reminders_api, name="active_reminders"),
    path("habits/reminders/test-push/", views.test_habit_reminder_push_api, name="test_habit_reminder_push"),
    path("push/subscribe/", views.push_subscribe_api, name="push_subscribe"),
]
