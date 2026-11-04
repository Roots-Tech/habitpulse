from datetime import date
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from habits.models import Habit, PixelRequest, PixelWallet
from habits.services import calculate_user_pixel_wallet
from tenants.models import Membership, Tenant


class PixelRedemptionRequestTests(TestCase):
    """
    Complete unit and integration tests for the Pixel Redemption Request workflow:
    1. Visual correction (single top crown logo in balance card, request button).
    2. User request creation and balance validation (max requestable <= available balance).
    3. Immediate wallet hold deduction upon request submission.
    4. Admin Requests page and permission enforcement (Super Admin only).
    5. Admin review full approval, partial approval (remainder refund), and decline (full refund).
    6. Complete transaction settlement tracking.
    """

    def setUp(self):
        self.client = Client()

        # Workspace
        self.tenant = Tenant.objects.create(
            name="Alpha HQ",
            slug="alpha-hq",
        )

        # Super Admin
        self.super_admin = User.objects.create_user(
            username="admin_boss",
            email="boss@alphahq.com",
            password="AdminPassword123!",
            role=User.Role.SUPER_ADMIN,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.super_admin,
            role="OWNER",
            status="ACTIVE",
        )

        # Regular User
        self.user = User.objects.create_user(
            username="john_regular",
            email="john@alphahq.com",
            password="UserPassword123!",
            role=User.Role.REGULAR_USER,
        )
        Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role="MEMBER",
            status="ACTIVE",
        )

        # Create active habit for john_regular so he has positive pixel balance
        self.habit = Habit.objects.create(
            tenant=self.tenant,
            created_by=self.user,
            name="Morning Run",
            frequency=Habit.Frequency.DAILY,
            start_date=timezone.localdate(),
            pixel_score=10,
            is_active=True,
        )

    def test_pixel_wallet_view_has_request_button(self):
        """
        The Pixel Wallet card displays the 'Raise Pixel Request' button linking to request form.
        """
        self.client.force_login(self.user)
        resp = self.client.get(reverse("pixel_wallet"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("pixel_request_create"))
        self.assertContains(resp, "Raise Pixel Request")

    def test_request_form_get_view(self):
        """
        GET /habits/pixel-wallet/request/ renders form with user's available balance.
        """
        self.client.force_login(self.user)
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        avail = wallet["current_balance"]

        resp = self.client.get(reverse("pixel_request_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"{avail}")
        self.assertContains(resp, "Raise Pixel Request")

    def test_request_amount_cannot_exceed_available_balance(self):
        """
        Submitting an amount greater than available balance is rejected with an error.
        """
        self.client.force_login(self.user)
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        avail = wallet["current_balance"]

        # Try requesting avail + 50 Px
        resp = self.client.post(reverse("pixel_request_create"), {
            "amount": str(avail + 50),
            "user_notes": "Attempting overdraft",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "exceeds your current available balance")
        self.assertFalse(PixelRequest.objects.filter(user=self.user).exists())

    def test_request_submission_immediate_wallet_hold(self):
        """
        Submitting a valid request creates a PENDING PixelRequest and
        immediately holds/deducts the amount from user's active wallet balance.
        """
        self.client.force_login(self.user)
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        initial_balance = wallet["current_balance"]
        self.assertGreater(initial_balance, 20)

        request_amount = 20
        resp = self.client.post(reverse("pixel_request_create"), {
            "amount": str(request_amount),
            "user_notes": "Redemption for gift voucher",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("pixel_wallet"))

        # Verify PixelRequest created
        req = PixelRequest.objects.filter(user=self.user).first()
        self.assertIsNotNone(req)
        self.assertEqual(req.status, PixelRequest.Status.PENDING)
        self.assertEqual(req.requested_amount, 20)
        self.assertEqual(req.held_balance, 20)
        self.assertEqual(req.wallet_balance_at_request, initial_balance)

        # Verify wallet immediately reflects deduction: initial_balance - 20
        new_wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        self.assertEqual(new_wallet["current_balance"], initial_balance - 20)

    def test_admin_pixel_requests_view_access(self):
        """
        Regular users are blocked (403), Super Admins can access (200).
        """
        # Regular user -> 403
        self.client.force_login(self.user)
        resp = self.client.get(reverse("admin_pixel_requests"))
        self.assertEqual(resp.status_code, 403)

        # Super Admin -> 200
        self.client.force_login(self.super_admin)
        resp = self.client.get(reverse("admin_pixel_requests"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pixel Redemption Requests")

    def test_admin_full_approval_workflow(self):
        """
        Admin fully approves the request:
        - status becomes APPROVED
        - held_balance becomes 0, approved_amount = requested_amount
        - wallet remains at the deducted balance
        - final_balance_after_settlement is saved
        """
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        initial_balance = wallet["current_balance"]

        req = PixelRequest.objects.create(
            tenant=self.tenant,
            user=self.user,
            wallet_balance_at_request=initial_balance,
            requested_amount=30,
            held_balance=30,
            status=PixelRequest.Status.PENDING,
            user_notes="Need 30 pixels",
        )

        self.client.force_login(self.super_admin)
        review_url = reverse("admin_pixel_request_review", kwargs={"request_id": req.pk})
        resp = self.client.post(review_url, {
            "decision": "approve",
            "admin_notes": "Fully approved. Enjoy!",
        })
        self.assertEqual(resp.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, PixelRequest.Status.APPROVED)
        self.assertEqual(req.approved_amount, 30)
        self.assertEqual(req.refunded_amount, 0)
        self.assertEqual(req.held_balance, 0)
        self.assertEqual(req.reviewed_by, self.super_admin)
        self.assertEqual(req.final_balance_after_settlement, initial_balance - 30)

        # User's wallet remains at initial_balance - 30
        new_wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        self.assertEqual(new_wallet["current_balance"], initial_balance - 30)

    def test_admin_partial_approval_workflow(self):
        """
        Admin decides to approve only a partial amount (e.g. 20 out of 50 Px):
        - status becomes PARTIALLY_APPROVED
        - approved_amount = 20, refunded_amount = 30
        - The unapproved remainder (30 Px) is refunded back to user's wallet
        """
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        initial_balance = wallet["current_balance"]

        req = PixelRequest.objects.create(
            tenant=self.tenant,
            user=self.user,
            wallet_balance_at_request=initial_balance,
            requested_amount=50,
            held_balance=50,
            status=PixelRequest.Status.PENDING,
            user_notes="Requested 50 Px",
        )

        self.client.force_login(self.super_admin)
        review_url = reverse("admin_pixel_request_review", kwargs={"request_id": req.pk})
        resp = self.client.post(review_url, {
            "decision": "partial",
            "partial_approved_amount": "20",
            "admin_notes": "Can only approve 20 Px for now; 30 Px refunded.",
        })
        self.assertEqual(resp.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, PixelRequest.Status.PARTIALLY_APPROVED)
        self.assertEqual(req.approved_amount, 20)
        self.assertEqual(req.refunded_amount, 30)
        self.assertEqual(req.held_balance, 0)
        self.assertEqual(req.final_balance_after_settlement, initial_balance - 20)

        # Wallet has 20 deducted, 30 refunded -> initial_balance - 20
        new_wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        self.assertEqual(new_wallet["current_balance"], initial_balance - 20)

    def test_admin_decline_workflow(self):
        """
        Admin declines the request:
        - status becomes DECLINED
        - approved_amount = 0, refunded_amount = requested_amount
        - Full requested amount is refunded back to user's wallet
        """
        wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        initial_balance = wallet["current_balance"]

        req = PixelRequest.objects.create(
            tenant=self.tenant,
            user=self.user,
            wallet_balance_at_request=initial_balance,
            requested_amount=40,
            held_balance=40,
            status=PixelRequest.Status.PENDING,
            user_notes="Request 40 Px",
        )

        self.client.force_login(self.super_admin)
        review_url = reverse("admin_pixel_request_review", kwargs={"request_id": req.pk})
        resp = self.client.post(review_url, {
            "decision": "decline",
            "admin_notes": "Redemption unavailable currently. Full refund.",
        })
        self.assertEqual(resp.status_code, 302)

        req.refresh_from_db()
        self.assertEqual(req.status, PixelRequest.Status.DECLINED)
        self.assertEqual(req.approved_amount, 0)
        self.assertEqual(req.refunded_amount, 40)
        self.assertEqual(req.held_balance, 0)
        self.assertEqual(req.final_balance_after_settlement, initial_balance)

        # Wallet is completely restored to initial balance
        new_wallet = calculate_user_pixel_wallet(self.user, tenant=self.tenant)
        self.assertEqual(new_wallet["current_balance"], initial_balance)
