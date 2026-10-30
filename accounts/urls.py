from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("settings/", views.general_settings_view, name="general_settings"),

    # Admin Panel - Users
    path("admin-panel/users/", views.admin_users_list_view, name="admin_users_list"),
    path("admin-panel/users/new/", views.admin_user_create_view, name="admin_user_create"),
    path("admin-panel/users/<int:user_id>/edit/", views.admin_user_edit_view, name="admin_user_edit"),
    path("admin-panel/users/<int:user_id>/delete/", views.admin_user_delete_view, name="admin_user_delete"),
    path("admin-panel/users/allocate-pixels/", views.admin_allocate_pixels_view, name="admin_allocate_pixels"),
    path("admin-panel/users/seed-admin-data/", views.admin_seed_data_view, name="admin_seed_data"),

    # Admin Panel - User Roles & Dynamic Permissions
    path("admin-panel/roles/", views.admin_roles_list_view, name="admin_roles_list"),
    path("admin-panel/roles/<str:role_code>/permissions/", views.admin_role_permissions_update_view, name="admin_role_permissions_update"),
    path("admin-panel/roles/<int:user_id>/change/", views.admin_user_role_change_view, name="admin_user_role_change"),
    path("admin-panel/roles/user/<int:user_id>/permissions/", views.admin_user_permissions_update_view, name="admin_user_permissions_update"),

    # Admin Panel - System Performance Meter & APM
    path("admin-panel/performance/", views.admin_performance_meter_view, name="admin_performance_meter"),
]
