import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.orchestrator.pipeline import handle_customer_message
from apps.orchestrator.tests.helpers import patch_roles
from apps.review.models import Chat, Message
from apps.security.llm import mock as llm_mock
from apps.tenants import runtime
from apps.tenants.models import ApiCall, TenantCustomer
from apps.tenants.tests.fakes import make_fake_client, patch_execution

User = get_user_model()


class TenantScenariosTests(TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.fake_client = make_fake_client(self.tmp_dir)
        self.p1, self.p2 = patch_execution(self.fake_client)
        self.p1.start()
        self.p2.start()
        runtime._context_cache.clear()

        self.user = User.objects.create_user("c101_user", password="testpass123")
        self.tenant_cust = TenantCustomer.objects.create(
            user=self.user, tenant="cloudbox", external_id="c-101"
        )
        self.chat = Chat.objects.create(
            customer=self.user, customer_name="Олена Коваль", subject="Оплата"
        )

    def tearDown(self):
        self.p1.stop()
        self.p2.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        runtime._context_cache.clear()

    def test_scenario_cloudbox_activation_issue(self):
        """c-101 paid for Plus but subscription is still Free. Agent syncs it."""
        # Step 1: read subscription, Step 2: read payments, Step 3: propose sync
        agent_steps = [
            {"type": "call", "endpoint": "get_subscription", "params": {}},
            {"type": "call", "endpoint": "get_payments", "params": {}},
            {
                "type": "call",
                "endpoint": "post_subscription_sync",
                "params": {},
                "body": {"payment_id": "pay-501"},
                "why": "Sync payment",
            },
        ]
        step_idx = 0

        def scripted_agent(user_prompt):
            nonlocal step_idx
            if step_idx < len(agent_steps):
                res = agent_steps[step_idx]
                step_idx += 1
                return res
            return {"type": "final", "reply": "Підписку активовано."}

        with patch_roles(agent=scripted_agent):
            msg = Message.objects.create(
                chat=self.chat, role="customer", text="Оплатив Plus, але доступ не з'явився"
            )
            outcome = handle_customer_message(self.chat, msg)

        self.assertEqual(outcome.decision, "execute")
        self.assertIn("Готово", outcome.reply)

        # Check mock database was modified
        sub_resp = self.fake_client.read("cloudbox.c-101.tok", "/subscription")
        self.assertEqual(sub_resp["data"]["plan"], "Plus")

        # Check ApiCall journal
        calls = list(ApiCall.objects.filter(customer="c-101").order_by("id"))
        kinds = [c.kind for c in calls]
        self.assertIn(ApiCall.READ, kinds)
        self.assertIn(ApiCall.PROPOSE, kinds)
        self.assertIn(ApiCall.EXECUTE, kinds)

    def test_scenario_refund_review_when_over_auto_limit(self):
        """90 грн refund is high risk or over auto limit -> review."""
        agent_steps = [
            {"type": "call", "endpoint": "get_payments", "params": {}},
            {
                "type": "call",
                "endpoint": "post_payments_payment_id_refund",
                "params": {"payment_id": "pay-501"},
                "body": {"amount": 90, "reason": "double charge"},
            },
        ]
        step_idx = 0

        def scripted_agent(user_prompt):
            nonlocal step_idx
            if step_idx < len(agent_steps):
                res = agent_steps[step_idx]
                step_idx += 1
                return res
            return {"type": "final", "reply": "Запит оброблено."}

        with patch_roles(agent=scripted_agent):
            msg = Message.objects.create(chat=self.chat, role="customer", text="Поверніть 90 грн")
            outcome = handle_customer_message(self.chat, msg)

        self.assertEqual(outcome.decision, "review")
        self.assertEqual(outcome.review["action"], "cloudbox.post_payments_payment_id_refund")
        self.assertEqual(outcome.review["params"]["amount"], 90)

    def test_scenario_refund_blocked_for_unseen_payment(self):
        """Trying to refund a payment ID not seen in customer's reads -> block (ownership)."""
        agent_steps = [
            {"type": "call", "endpoint": "get_payments", "params": {}},
            {
                "type": "call",
                "endpoint": "post_payments_payment_id_refund",
                "params": {"payment_id": "pay-999-other"},
                "body": {"amount": 30, "reason": "refund"},
            },
        ]
        step_idx = 0

        def scripted_agent(user_prompt):
            nonlocal step_idx
            if step_idx < len(agent_steps):
                res = agent_steps[step_idx]
                step_idx += 1
                return res
            return {"type": "final", "reply": "ok"}

        with patch_roles(agent=scripted_agent):
            msg = Message.objects.create(
                chat=self.chat, role="customer", text="Поверніть за pay-999-other"
            )
            outcome = handle_customer_message(self.chat, msg)

        self.assertEqual(outcome.decision, "block")

    def test_token_safety_token_never_leaks(self):
        """Tokens or API keys never appear in prompts, trace, or ApiCall logs."""
        prompts_seen = []
        real_respond = llm_mock.respond

        def recording_respond(role, system, user):
            prompts_seen.append(system + "\n" + user)
            return real_respond(role, system, user)

        with mock.patch.object(llm_mock, "respond", side_effect=recording_respond):
            msg = Message.objects.create(chat=self.chat, role="customer", text="Який у мене тариф?")
            outcome = handle_customer_message(self.chat, msg)

        # Check all captured prompts
        for p in prompts_seen:
            self.assertNotIn("test-execution-key", p)
            self.assertNotIn("fake-token", p)

        # Check ApiCall records
        for call in ApiCall.objects.all():
            self.assertNotIn("test-execution-key", str(call.request))
            self.assertNotIn("test-execution-key", str(call.response))

        # Check trace
        for step in outcome.trace:
            self.assertNotIn("test-execution-key", str(step))
            self.assertNotIn("fake-token", str(step))

    def test_loop_limit_escalates_to_human(self):
        """An agent that endlessly reads hits TENANT_AGENT_MAX_STEPS and escalates."""

        def endless_reader(user_prompt):
            return {"type": "call", "endpoint": "get_subscription", "params": {}}

        with patch_roles(agent=endless_reader):
            msg = Message.objects.create(chat=self.chat, role="customer", text="Перевір мій статус")
            outcome = handle_customer_message(self.chat, msg)

        self.assertEqual(outcome.decision, "review")
        self.assertIn("loop limit", outcome.reason)

    def test_shopx_order_cancellation(self):
        """Second product (ShopX): cancels processing order 1042 cleanly."""
        shop_user = User.objects.create_user("s201_user", password="testpass123")
        TenantCustomer.objects.create(user=shop_user, tenant="shopx", external_id="s-201")
        shop_chat = Chat.objects.create(
            customer=shop_user, customer_name="Іван", subject="Замовлення"
        )

        agent_steps = [
            {"type": "call", "endpoint": "get_orders", "params": {}},
            {
                "type": "call",
                "endpoint": "post_orders_number_cancel",
                "params": {"number": "1042"},
                "body": {},
                "why": "Cancel order",
            },
        ]
        step_idx = 0

        def shop_agent(user_prompt):
            nonlocal step_idx
            if step_idx < len(agent_steps):
                res = agent_steps[step_idx]
                step_idx += 1
                return res
            return {"type": "final", "reply": "Замовлення скасовано."}

        with patch_roles(agent=shop_agent):
            msg = Message.objects.create(
                chat=shop_chat, role="customer", text="Скасуйте замовлення 1042"
            )
            outcome = handle_customer_message(shop_chat, msg)

        self.assertEqual(outcome.decision, "execute")
        self.assertIn("Готово", outcome.reply)
