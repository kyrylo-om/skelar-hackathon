from pathlib import Path

from django.test import SimpleTestCase

from apps.tenants.endpoints import EndpointError, build_path, check_body, parse_api


class EndpointsTests(SimpleTestCase):
    def test_parse_cloudbox_context(self):
        repo_root = Path(__file__).resolve().parents[4]
        text = (repo_root / "mocks" / "cloudbox" / "context.md").read_text(encoding="utf-8")
        endpoints = parse_api(text)
        self.assertIn("get_me", endpoints)
        self.assertIn("get_subscription", endpoints)
        self.assertIn("get_payments", endpoints)
        self.assertIn("post_subscription_sync", endpoints)
        self.assertIn("post_payments_payment_id_refund", endpoints)

        sync = endpoints["post_subscription_sync"]
        self.assertEqual(sync.method, "POST")
        self.assertEqual(sync.kind, "write")
        self.assertEqual(sync.body_example, {"payment_id": "pay-501"})

    def test_parse_shopx_context(self):
        repo_root = Path(__file__).resolve().parents[4]
        text = (repo_root / "mocks" / "shopx" / "context.md").read_text(encoding="utf-8")
        endpoints = parse_api(text)
        self.assertIn("get_me", endpoints)
        self.assertIn("get_orders", endpoints)
        self.assertIn("get_orders_number", endpoints)
        self.assertIn("post_orders_number_cancel", endpoints)
        self.assertIn("patch_orders_number_address", endpoints)
        self.assertIn("post_orders_number_refund", endpoints)

    def test_build_path_valid(self):
        context = (
            "| Method | Path | Body | Result |\n|---|---|---|---|\n| GET | `/items/{id}` | | item |"
        )
        ep = parse_api(context)["get_items_id"]
        path = build_path(ep, {"id": "item-123"})
        self.assertEqual(path, "/items/item-123")

    def test_build_path_rejects_missing_var(self):
        context = (
            "| Method | Path | Body | Result |\n|---|---|---|---|\n| GET | `/items/{id}` | | item |"
        )
        ep = parse_api(context)["get_items_id"]
        with self.assertRaises(EndpointError):
            build_path(ep, {})

    def test_build_path_rejects_path_traversal(self):
        context = (
            "| Method | Path | Body | Result |\n|---|---|---|---|\n| GET | `/items/{id}` | | item |"
        )
        ep = parse_api(context)["get_items_id"]
        with self.assertRaises(EndpointError):
            build_path(ep, {"id": "../secret"})

    def test_check_body_valid(self):
        context = (
            "| Method | Path | Body | Result |\n"
            "|---|---|---|---|\n"
            '| POST | `/items` | `{"name": "test", "qty": 1}` | item |'
        )
        ep = parse_api(context)["post_items"]
        check_body(ep, {"name": "book", "qty": 5})

    def test_check_body_rejects_unknown_field(self):
        context = (
            "| Method | Path | Body | Result |\n"
            "|---|---|---|---|\n"
            '| POST | `/items` | `{"name": "test"}` | item |'
        )
        ep = parse_api(context)["post_items"]
        with self.assertRaises(EndpointError):
            check_body(ep, {"name": "book", "extra": "field"})

    def test_check_body_rejects_type_mismatch(self):
        context = (
            "| Method | Path | Body | Result |\n"
            "|---|---|---|---|\n"
            '| POST | `/items` | `{"qty": 10}` | item |'
        )
        ep = parse_api(context)["post_items"]
        with self.assertRaises(EndpointError):
            check_body(ep, {"qty": "not-a-number"})
