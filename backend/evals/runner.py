"""Scenario evaluation runner through the full production pipeline."""

import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import yaml
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.orchestrator.pipeline import handle_customer_message
from apps.review.models import Chat, Message
from apps.security.models import ActionLog, AgentAudit
from apps.subscriptions.models import Payment, Plan, Subscription
from apps.tenants import runtime as tenants_runtime
from apps.tenants.models import TenantCustomer
from apps.tenants.tests.fakes import make_fake_client, patch_execution

User = get_user_model()


def load_scenarios(
    scenarios_dir: Path | str | None = None, tag: str | None = None, tenant: str | None = None
) -> list[dict]:
    base = Path(scenarios_dir or Path(__file__).parent / "scenarios")
    scenarios = []
    for file in sorted(base.glob("*.yaml")):
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or []
        for item in data:
            if tag and tag not in item.get("tag", []):
                continue
            if tenant and item.get("tenant") != tenant:
                continue
            scenarios.append(item)
    return scenarios


def setup_customer(scenario: dict) -> object:
    """Set up customer user with proper facts according to tenant and customer id."""
    cust_id = scenario.get("customer", "ivan")
    tenant = scenario.get("tenant", "streamflow")
    username = f"eval_{tenant}_{cust_id}"

    user, _ = User.objects.get_or_create(username=username, defaults={"is_staff": False})
    # Reset actions and logs for isolated run
    ActionLog.objects.filter(customer_id=user.pk).delete()

    if tenant in ("cloudbox", "shopx"):
        TenantCustomer.objects.update_or_create(
            user=user, defaults={"tenant": tenant, "external_id": cust_id}
        )
    else:
        # Standard dev domain
        TenantCustomer.objects.filter(user=user).delete()
        free, _ = Plan.objects.get_or_create(
            name="Free", defaults={"price": 0, "storage_limit_gb": 5}
        )
        plus, _ = Plan.objects.get_or_create(
            name="Plus", defaults={"price": 99, "storage_limit_gb": 100}
        )
        now = timezone.now()
        Subscription.objects.get_or_create(
            user=user,
            defaults={"plan": plus, "auto_renew": True, "period_end": now + timedelta(days=29)},
        )
        Payment.objects.get_or_create(
            user=user,
            defaults={
                "plan": plus,
                "amount": 99,
                "status": "successful",
                "period_start": now - timedelta(days=1),
                "period_end": now + timedelta(days=29),
            },
        )
    return user


def evaluate_run(scenario: dict, mode: str = "mock") -> dict:
    user = setup_customer(scenario)
    chat = Chat.objects.create(
        customer=user, customer_name=user.username, subject=f"Eval {scenario['id']}"
    )

    expect = scenario.get("expect") or {}
    turns = scenario.get("turns") or []

    llm_audit_before = AgentAudit.objects.count()
    start_time = time.monotonic()
    outcome = None
    all_trace = []

    for turn in turns:
        msg = Message.objects.create(chat=chat, role="customer", text=turn.get("say", ""))
        outcome = handle_customer_message(chat, msg)
        all_trace.extend(outcome.trace)

    duration_ms = int((time.monotonic() - start_time) * 1000)
    llm_calls = AgentAudit.objects.count() - llm_audit_before

    # Check assertions
    errors = []
    actual_decision = outcome.decision if outcome else "unknown"
    actual_reply = outcome.reply if outcome else ""

    # 1. Decision check
    expected_decision = expect.get("decision")
    if expected_decision and actual_decision != expected_decision:
        errors.append(f"Expected decision {expected_decision!r}, got {actual_decision!r}")

    # 2. Blocked by check
    blocked_by = None
    for step in all_trace:
        verdict = step.get("verdict", "")
        if verdict in ("block", "reject", "deny", "needs_review"):
            blocked_by = step.get("agent")
            break

    expected_blocked_by = expect.get("blocked_by")
    if expected_blocked_by and blocked_by != expected_blocked_by:
        errors.append(f"Expected blocked_by {expected_blocked_by!r}, got {blocked_by!r}")

    # 3. Guard verdict check
    guard_step = next((s for s in all_trace if s.get("agent") == "guard"), None)
    expected_guard = expect.get("guard")
    if expected_guard and guard_step and guard_step.get("verdict") != expected_guard:
        errors.append(f"Expected guard {expected_guard!r}, got {guard_step.get('verdict')!r}")

    # 4. Reply must not contain
    reply_lower = actual_reply.lower()
    for forbidden in expect.get("reply_must_not_contain") or []:
        if forbidden.lower() in reply_lower:
            errors.append(f"Reply contains forbidden text: {forbidden!r}")

    # 5. Reply must contain any
    required_any = expect.get("reply_must_contain_any") or []
    if required_any and not any(req.lower() in reply_lower for req in required_any):
        errors.append(f"Reply does not contain any of required: {required_any!r}")

    # 6. Forbidden actions
    executed_actions = [o.action for o in getattr(outcome, "turn_outcomes", [])]
    if outcome and outcome.review:
        executed_actions.append(outcome.review.get("action"))
    for forb in expect.get("forbidden_actions") or []:
        if forb in executed_actions:
            errors.append(f"Forbidden action {forb!r} was proposed or executed")

    passed = len(errors) == 0

    return {
        "id": scenario["id"],
        "tags": scenario.get("tag", []),
        "passed": passed,
        "errors": errors,
        "expected_decision": expected_decision,
        "actual_decision": actual_decision,
        "blocked_by": blocked_by,
        "duration_ms": duration_ms,
        "llm_calls": llm_calls,
        "actions": executed_actions,
        "reply": actual_reply,
        "trace": all_trace,
    }


def run_all(
    scenarios: list[dict],
    mode: str = "mock",
    repeat: int = 1,
    fake_client=None,
) -> tuple[dict, list[dict]]:
    """Execute scenario suite, calculate statistics and stability."""
    results = []

    # If mock mode, force mock LLM provider
    old_provider = getattr(settings, "LLM_PROVIDER", "mock")
    patches = []
    tmp_dir = None
    if mode == "mock":
        settings.LLM_PROVIDER = "mock"

    # Ensure connected products have execution backend available
    if not getattr(settings, "EXECUTION_SERVICE_KEY", None) or fake_client is not None:
        tmp_dir = Path(tempfile.mkdtemp())
        client = fake_client or make_fake_client(tmp_dir)
        p1, p2 = patch_execution(client)
        p1.start()
        p2.start()
        patches = [p1, p2]
        tenants_runtime._context_cache.clear()

    try:
        for scen in scenarios:
            runs = []
            for _ in range(repeat):
                run_res = evaluate_run(scen, mode=mode)
                runs.append(run_res)

            # Aggregate over repeats
            passed_count = sum(1 for r in runs if r["passed"])
            stability = (passed_count / repeat) * 100
            final_res = dict(runs[0])
            final_res["stability"] = stability
            final_res["passed"] = passed_count == repeat
            results.append(final_res)
    finally:
        for p in patches:
            p.stop()
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        tenants_runtime._context_cache.clear()
        settings.LLM_PROVIDER = old_provider

    # Aggregate summary
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total else 0.0

    security_scenarios = [r for r in results if "security" in r.get("tags", [])]
    total_attacks = len(security_scenarios)
    attacks_blocked = sum(1 for r in security_scenarios if r["actual_decision"] == "block")

    fp_scenarios = [r for r in results if "false_positive" in r.get("tags", [])]
    false_positives = sum(1 for r in fp_scenarios if r["actual_decision"] == "block")

    guard_blocks = sum(1 for r in results if r.get("blocked_by") == "guard")
    critic_blocks = sum(1 for r in results if r.get("blocked_by") == "critic")
    policy_blocks = sum(1 for r in results if r.get("blocked_by") == "policy")

    durations = [r.get("duration_ms", 0) for r in results]
    avg_ms = sum(durations) / total if total else 0
    sorted_durations = sorted(durations)
    p95_idx = int(0.95 * total)
    p95_ms = sorted_durations[p95_idx] if sorted_durations else 0

    llm_calls_list = [r.get("llm_calls", 0) for r in results]
    avg_llm_calls = sum(llm_calls_list) / total if total else 0

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "total_attacks": total_attacks,
        "attacks_blocked": attacks_blocked,
        "false_positives": false_positives,
        "guard_blocks": guard_blocks,
        "critic_blocks": critic_blocks,
        "policy_blocks": policy_blocks,
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
        "avg_llm_calls": avg_llm_calls,
    }

    return summary, results
