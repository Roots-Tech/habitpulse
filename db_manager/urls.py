from django.urls import path
from db_manager.views import (
    db_manager_auth_view,
    db_manager_create_view,
    db_manager_drop_view,
    db_manager_index_view,
    db_manager_instance_info_view,
    db_manager_logout_view,
)

urlpatterns = [
    path("", db_manager_index_view, name="db_manager_index"),
    path("instance-info/", db_manager_instance_info_view, name="db_manager_instance_info"),
    path("auth/", db_manager_auth_view, name="db_manager_auth"),
    path("logout/", db_manager_logout_view, name="db_manager_logout"),
    path("create/", db_manager_create_view, name="db_manager_create"),
    path("drop/", db_manager_drop_view, name="db_manager_drop"),
]
