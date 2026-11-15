import io
from datetime import date
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from habits.models import Habit, HabitCompletion
from habits.validators import EvidenceFileValidator
from tenants.models import Tenant, Membership

User = get_user_model()


class AuditRemediationPhase1Tests(TestCase):
    """Automated verification for Phase 1 Technical Audit Remediations."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="audit_testuser",
            email="audit@example.com",
            password="SecurePassword123!",
        )
        self.tenant = Tenant.objects.create(
            name="Audit Test Workspace",
            slug="audit-test-ws",
        )
        Membership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role="OWNER",
        )
        self.habit = Habit.objects.create(
            tenant=self.tenant,
            name="Daily Pushups",
            created_by=self.user,
            frequency=Habit.Frequency.DAILY,
            start_date=date.today(),
            is_active=True,
            enable_evidence_upload=True,
            enable_ai_proof_verification=False,
        )
        self.client.force_login(self.user)

    def test_api_01_idempotent_completion_on_duplicate_submit(self):
        """API-01: Verifies rapid double-click submissions return HTTP 200 with idempotent state instead of HTTP 500."""
        # Use standard habit without evidence for simple completion test
        self.habit.enable_evidence_upload = False
        self.habit.save()

        url = reverse("api:habit_complete", kwargs={"pk": self.habit.pk})

        session = self.client.session
        session["active_tenant_id"] = self.tenant.pk
        session.save()

        # First request succeeds
        res1 = self.client.post(url, {"date": str(date.today())})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertTrue(data1["success"])
        self.assertFalse(data1.get("idempotent", False))

        # Immediate duplicate submission (simulating double-click or network retry)
        res2 = self.client.post(url, {"date": str(date.today())})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2["success"])
        self.assertTrue(data2.get("idempotent", False))
        self.assertIn("already completed", data2["message"])

        # Ensure only 1 completion record exists in database
        self.assertEqual(
            HabitCompletion.objects.filter(habit=self.habit, completion_date=date.today()).count(),
            1,
        )

    def test_sec_04_file_magic_byte_validation(self):
        """SEC-04: Rejects disguised executables/scripts named as .png/.pdf."""
        validator = EvidenceFileValidator()

        # 1. Fake PNG file with plaintext script content
        fake_png = SimpleUploadedFile(
            name="exploit.png",
            content=b"malicious executable or script payload disguised as image",
            content_type="image/png",
        )
        result_fake = validator.validate(self.habit, {}, {"evidence_file": fake_png})
        self.assertFalse(result_fake.is_valid)
        self.assertIn("Invalid or corrupted file content", result_fake.error_message)

        # 2. Genuine PNG file with valid magic bytes
        real_png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        valid_png = SimpleUploadedFile(
            name="valid_photo.png",
            content=real_png_header,
            content_type="image/png",
        )
        result_valid = validator.validate(self.habit, {}, {"evidence_file": valid_png})
        self.assertTrue(result_valid.is_valid)

        # 3. Genuine PDF file with valid %PDF header
        valid_pdf = SimpleUploadedFile(
            name="report.pdf",
            content=b"%PDF-1.4 header contents for document",
            content_type="application/pdf",
        )
        result_pdf = validator.validate(self.habit, {}, {"evidence_file": valid_pdf})
        self.assertTrue(result_pdf.is_valid)

    def test_sec_05_login_rate_limiting_lockout(self):
        """SEC-05: Verifies that 5 consecutive failed login attempts trigger lockout."""
        self.client.logout()
        login_url = reverse("login")

        # 5 failed attempts
        for i in range(5):
            res = self.client.post(login_url, {
                "username": "audit_testuser",
                "password": "WrongPassword!",
            })
            self.assertEqual(res.status_code, 200)

        # 6th attempt should be locked out
        res6 = self.client.post(login_url, {
            "username": "audit_testuser",
            "password": "SecurePassword123!",
        })
        self.assertEqual(res6.status_code, 200)
        self.assertContains(res6, "Too many failed login attempts")

    @override_settings(DEBUG=False)
    def test_perf_04_tracemalloc_disabled_in_production(self):
        """PERF-04: Verifies tracemalloc is not initiated when DEBUG=False."""
        import tracemalloc
        from config.performance import PerformanceTracker

        if tracemalloc.is_tracing():
            tracemalloc.stop()

        tracker = PerformanceTracker()
        self.assertFalse(tracemalloc.is_tracing())

    def test_neutralized_clear_habit_data_command(self):
        """Zero Data Loss: Verifies clear_habit_data command blocks purging and keeps records intact."""
        out = io.StringIO()
        call_command("clear_habit_data", stdout=out)
        output = out.getvalue()

        self.assertIn("ACTION BLOCKED", output)
        self.assertIn("Zero Data Loss Policy", output)
        # Habits remain completely intact
        self.assertTrue(Habit.objects.filter(pk=self.habit.pk).exists())
