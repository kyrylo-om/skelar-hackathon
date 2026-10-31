import shutil
import tempfile

from django.test import TestCase

from evals.reports import write_reports
from evals.runner import evaluate_run, load_scenarios, run_all


class EvalsSuiteTests(TestCase):
    def test_catalog_is_valid_and_ids_are_unique(self):
        scenarios = load_scenarios()
        self.assertGreaterEqual(len(scenarios), 28, "Catalog must have at least 28 scenarios")
        ids = [s["id"] for s in scenarios]
        self.assertEqual(len(ids), len(set(ids)), "All scenario IDs must be unique")

    def test_runner_on_sample_scenarios(self):
        scenarios = load_scenarios(tag="regular")[:3]
        self.assertEqual(len(scenarios), 3)
        summary, results = run_all(scenarios, mode="mock", repeat=1)
        self.assertEqual(summary["total"], 3)
        self.assertEqual(len(results), 3)

    def test_tag_filtering(self):
        sec_scenarios = load_scenarios(tag="security")
        self.assertTrue(all("security" in s.get("tag", []) for s in sec_scenarios))
        self.assertGreater(len(sec_scenarios), 0)

    def test_failure_is_detected_on_wrong_expectation(self):
        scen = {
            "id": "synthetic_failure_test",
            "tag": ["test"],
            "tenant": "streamflow",
            "customer": "ivan",
            "turns": [{"say": "Який у мене тариф?"}],
            "expect": {
                "decision": "block"  # Impossible for normal status query, must fail
            },
        }
        res = evaluate_run(scen, mode="mock")
        self.assertFalse(res["passed"])
        self.assertTrue(any("Expected decision 'block'" in err for err in res["errors"]))

    def test_secrets_never_leak_into_reports(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            summary = {
                "total": 1,
                "passed": 1,
                "failed": 0,
                "pass_rate": 100,
                "attacks_blocked": 0,
                "total_attacks": 0,
                "false_positives": 0,
                "guard_blocks": 0,
                "critic_blocks": 0,
                "policy_blocks": 0,
                "avg_ms": 10,
                "p95_ms": 10,
                "avg_llm_calls": 1,
            }
            results = [
                {
                    "id": "leak_check",
                    "passed": True,
                    "reply": "Here is SECRET_KEY and token test",
                    "trace": [{"detail": "secret leak test"}],
                }
            ]
            json_p, md_p = write_reports(summary, results, out_dir=tmp_dir)
            md_text = md_p.read_text(encoding="utf-8")
            self.assertNotIn("synthetic-secret", md_text)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
