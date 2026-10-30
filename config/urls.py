from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView, TemplateView
from config.views import protected_media_view


class ServiceWorkerView(TemplateView):
    template_name = "pwa/sw.js"
    content_type = "application/javascript"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response["Service-Worker-Allowed"] = "/"
        response["Cache-Control"] = "no-cache"
        return response


class ManifestView(TemplateView):
    template_name = "pwa/manifest.json"
    content_type = "application/manifest+json"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response["Cache-Control"] = "public, max-age=86400"
        return response


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("api/v1/", include("api.urls")),
    path("admin-panel/performance/", RedirectView.as_view(pattern_name="admin_performance_meter", permanent=False)),
    path("admin-panel/users/", RedirectView.as_view(pattern_name="admin_users_list", permanent=False)),
    path("admin-panel/roles/", RedirectView.as_view(pattern_name="admin_roles_list", permanent=False)),
    # PWA Endpoints
    path("manifest.json", ManifestView.as_view(), name="pwa_manifest"),
    path("sw.js", ServiceWorkerView.as_view(), name="pwa_service_worker"),
    path("offline/", TemplateView.as_view(template_name="pwa/offline.html"), name="pwa_offline"),
    path("", include("habits.urls")),
    path("", include("dashboard.urls")),
    re_path(r"^media/(?P<path>.*)$", protected_media_view, name="protected_media"),
]
