from django.test import SimpleTestCase

from apps.tenants.manifest import ManifestError, build_tenant, parse_rules


class ManifestTests(SimpleTestCase):
    def test_parses_valid_manifest(self):
        yaml_text = """
tenant: testapp
name: Test App
policies:
  rate_limit_per_hour: 10
  idempotency_window_sec: 60
  review_vip: false
rules:
  - match: "POST /items"
    risk: low
    summary: "Create item"
  - match: "POST /items/{id}/refund"
    risk: high
    summary: "Refund {amount}"
    limits:
      amount_param: amount
      auto_max: 50
      hard_max: 1000
    requires:
      - read: "GET /items"
        where:
          id: "{id}"
        field: status
        in: [active]
"""
        rules = parse_rules(yaml_text)
        self.assertEqual(rules.tenant, "testapp")
        self.assertEqual(rules.rate_limit_per_hour, 10)
        self.assertFalse(rules.review_vip)
        self.assertIn("POST /items", rules.rules)
        self.assertIn("POST /items/{id}/refund", rules.rules)
        self.assertEqual(rules.rules["POST /items/{id}/refund"].auto_max, 50)

    def test_rejects_missing_tenant(self):
        with self.assertRaises(ManifestError):
            parse_rules("name: Only Name\nrules: []")

    def test_rejects_invalid_risk(self):
        with self.assertRaises(ManifestError):
            parse_rules("""
tenant: testapp
rules:
  - match: "POST /x"
    risk: critical
""")

    def test_rejects_auto_max_greater_than_hard_max(self):
        with self.assertRaises(ManifestError):
            parse_rules("""
tenant: testapp
rules:
  - match: "POST /x"
    risk: high
    limits:
      amount_param: amount
      auto_max: 200
      hard_max: 100
""")

    def test_rejects_limits_without_amount_param(self):
        with self.assertRaises(ManifestError):
            parse_rules("""
tenant: testapp
rules:
  - match: "POST /x"
    risk: high
    limits:
      auto_max: 50
      hard_max: 100
""")

    def test_rejects_duplicate_rule(self):
        with self.assertRaises(ManifestError):
            parse_rules("""
tenant: testapp
rules:
  - match: "POST /x"
    risk: low
  - match: "POST /x"
    risk: high
""")

    def test_build_tenant_rejects_unknown_rule_match(self):
        context = """
# App
| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/items` | | items |
"""
        rules = parse_rules("""
tenant: testapp
rules:
  - match: "POST /unknown"
    risk: low
""")
        with self.assertRaises(ManifestError):
            build_tenant(rules, context)

    def test_build_tenant_rejects_requirement_reading_non_get(self):
        context = """
# App
| Method | Path | Body | Result |
|---|---|---|---|
| POST | `/items` | `{"id": "1"}` | items |
"""
        rules = parse_rules("""
tenant: testapp
rules:
  - match: "POST /items"
    risk: low
    requires:
      - read: "POST /items"
        where: {id: "1"}
        field: status
        in: [ok]
""")
        with self.assertRaises(ManifestError):
            build_tenant(rules, context)
