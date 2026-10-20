from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    path("dashboard/", views.dashboard_api, name="dashboard"),
    path("habits/<int:pk>/complete/", views.habit_complete_api, name="habit_complete"),
    path("habits/<int:pk>/undo/", views.habit_undo_api, name="habit_undo"),
    path("habits/<int:pk>/status/", views.habit_status_api, name="habit_status"),
    path("users/", views.users_list_api, name="users_list"),
]
