import time
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.http import HttpResponse

from config.performance import (
    PerformanceTracker,
    profile_function,
    PerformanceMonitoringMiddleware,
    performance_tracker,
)
from tenants.utils import create_personal_workspace_for_user

User = get_user_model()


class PerformanceMeterTestCase(TestCase):
    def setUp(self):
        performance_tracker.reset()

        self.super_user = User.objects.create_user(
            username="perf_super",
            email="super@example.com",
            password="Password123!",
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.super_tenant, _ = create_personal_workspace_for_user(self.super_user, "Super Workspace")

        self.regular_user = User.objects.create_user(
            username="perf_regular",
            email="regular@example.com",
            password="Password123!",
        )
        self.regular_tenant, _ = create_personal_workspace_for_user(self.regular_user, "Regular Workspace")

    def tearDown(self):
        performance_tracker.reset()

    def test_performance_tracker_records_requests(self):
        """Tracker properly aggregates calls, latencies, and DB counts."""
        performance_tracker.record_request(
            path="/habits/",
            view_name="habit_list_view",
            method="GET",
            status_code=200,
            duration_ms=45.0,
            query_count=3,
            db_time_ms=8.5,
        )

        metrics = performance_tracker.get_metrics()
        self.assertEqual(metrics["total_requests"], 1)
        self.assertEqual(metrics["avg_latency_ms"], 45.0)
        self.assertEqual(metrics["avg_queries_per_req"], 3.0)
        self.assertGreaterEqual(metrics["health_score"], 80)

        endpoint_data = next((ep for ep in metrics["endpoints"] if ep["endpoint"] == "GET /habits/"), None)
        self.assertIsNotNone(endpoint_data)
        self.assertEqual(endpoint_data["calls"], 1)
        self.assertEqual(endpoint_data["avg_ms"], 45.0)

    def test_profile_function_decorator(self):
        """profile_function records invocation counts and execution durations."""
        @profile_function("test_benchmark_func")
        def heavy_math():
            time.sleep(0.01)
            return 42

        result = heavy_math()
        self.assertEqual(result, 42)

        metrics = performance_tracker.get_metrics()
        fn_data = next((fn for fn in metrics["functions"] if fn["function_name"] == "test_benchmark_func"), None)
        self.assertIsNotNone(fn_data)
        self.assertEqual(fn_data["calls"], 1)
        self.assertGreater(fn_data["avg_ms"], 5.0)

    def test_performance_middleware_attaches_server_timing(self):
        """Middleware tracks real requests and attaches Server-Timing header."""
        rf = RequestFactory()
        req = rf.get("/api/v1/dashboard/")
        middleware = PerformanceMonitoringMiddleware(get_response=lambda r: HttpResponse("OK"))

        resp = middleware(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Server-Timing", resp)
        self.assertIn("total;dur=", resp["Server-Timing"])

    def test_admin_performance_meter_view_permissions(self):
        """Only admins/super admins can view the performance meter."""
        url = reverse("admin_performance_meter")

        # Regular user -> 403 Forbidden
        self.client.login(username="regular@example.com", password="Password123!")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

        # Super admin -> 200 OK
        self.client.login(username="super@example.com", password="Password123!")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("metrics", resp.context)
        self.assertIn("System Performance Meter", resp.content.decode())

    def test_admin_performance_api_and_reset(self):
        """Test GET and POST reset endpoints for APM."""
        api_url = reverse("api:admin_performance")
        reset_url = reverse("api:admin_performance_reset")

        # Unauthenticated -> 401
        self.assertEqual(self.client.get(api_url).status_code, 401)
        self.assertEqual(self.client.post(reset_url).status_code, 401)

        # Super admin -> 200 OK
        self.client.login(username="super@example.com", password="Password123!")
        resp = self.client.get(api_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("health_score", data["data"])

        # Reset -> 200 OK
        resp_reset = self.client.post(reset_url)
        self.assertEqual(resp_reset.status_code, 200)
        self.assertEqual(resp_reset.json()["status"], "success")
