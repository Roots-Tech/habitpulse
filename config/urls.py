from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("api/v1/", include("api.urls")),
    path("admin-panel/performance/", RedirectView.as_view(pattern_name="admin_performance_meter", permanent=False)),
    path("admin-panel/users/", RedirectView.as_view(pattern_name="admin_users_list", permanent=False)),
    path("admin-panel/roles/", RedirectView.as_view(pattern_name="admin_roles_list", permanent=False)),
    path("", include("habits.urls")),
    path("", include("dashboard.urls")),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
