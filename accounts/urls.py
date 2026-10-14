from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Admin Panel - Users
    path("admin-panel/users/", views.admin_users_list_view, name="admin_users_list"),
    path("admin-panel/users/new/", views.admin_user_create_view, name="admin_user_create"),
    path("admin-panel/users/<int:user_id>/edit/", views.admin_user_edit_view, name="admin_user_edit"),
    path("admin-panel/users/<int:user_id>/delete/", views.admin_user_delete_view, name="admin_user_delete"),

    # Admin Panel - User Roles
    path("admin-panel/roles/", views.admin_roles_list_view, name="admin_roles_list"),
    path("admin-panel/roles/<int:user_id>/change/", views.admin_user_role_change_view, name="admin_user_role_change"),
]
