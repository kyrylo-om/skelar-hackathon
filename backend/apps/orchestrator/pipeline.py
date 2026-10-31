"""The orchestrator: one customer message in, one safe outcome out.

    Guard -> Triage -> Actor -> Critic -> Policy -> (execute | human review | refuse | ask)

Every LLM answer is validated and every failure falls back to something more cautious: unclear
requests are asked about, broken plans go to a human, refused actions are refused. Nothing the
model says reaches the product except through Gate and the gateway.
"""

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.review import services as review
from apps.review.models import Chat, ReviewItem
from apps.review.ports import ExecutionError
from apps.security import policy, router
from apps.security.contracts import BLOCK, CLARIFY, EXECUTE, REVIEW, trace_step
from apps.security.gate import gate_plan, screen_input
from apps.security.llm import message_budget

from . import facts as product
from . import plan as planning
from . import responder
from .gateway import AWAITING, DONE, FAILED, ActionOutcome, Busy, DevDomainGateway
from .manifest import OUT_OF_SCOPE, SERVICE_INTENTS, SMALLTALK, UNCLEAR, Manifest, get_manifest
from .mcp_gateway import McpGateway, ProductUnavailable
from .models import TurnState

logger = logging.getLogger("apps.orchestrator")
PRIORITY = {"low": Chat.Priority.LOW, "normal": Chat.Priority.NORMAL, "high": Chat.Priority.HIGH}


@dataclass
class Outcome:
    decision: str  # execute | review | block | clarify | busy
    reply: str
    trace: list = field(default_factory=list)
    intent: str = ""
    priority: str = "normal"
    reason: str = ""
    review: dict | None = None  # {"action", "params", "risk", "reason"} to open for a human
    summary: str = ""
    reset_clarifications: bool = False


def _gateway(user):
    """The product this deployment acts on: the built-in dev domain, or one behind MCP."""
    if settings.ORCHESTRATOR_GATEWAY == "mcp":
        return McpGateway(user)
    return DevDomainGateway(user)


def _summary(masked: str, intent: str, reason: str) -> str:
    return (
        f"Запит клієнта (без персональних даних): {masked[:300]}\n"
        f"Інтент: {intent}.\nПричина: {reason}"
    )


def _review_request(action: str, params: dict, reason: str) -> dict:
    return {
        "action": action,
        "params": params,
        "risk": policy.ACTIONS.get(action, {}).get("risk", "high"),
        "reason": reason,
    }


def _handoff(
    manifest, trace, masked, intent, priority, reason, action="escalate_to_human", params=None
):
    trace = [*trace, trace_step("human", "needs_review", reason)]
    return Outcome(
        "review",
        manifest.responses["review"],
        trace,
        intent,
        priority,
        reason,
        review=_review_request(action, params or {"reason": reason}, reason),
        summary=_summary(masked, intent, reason),
        reset_clarifications=True,
    )


def _triage(masked: str, state: TurnState, manifest: Manifest) -> dict:
    esc = manifest.escalation
    raw = router.route(
        "triage",
        {
            "context": {
                "intents": manifest.intent_ids(),
                "clarifications_used": state.clarifications_used,
            },
            "customer_message": masked,
        },
    )
    intent = raw.get("intent")
    confidence = raw.get("confidence", 1.0)
    if raw.get("_fallback") or intent not in {*manifest.intents, *SERVICE_INTENTS}:
        intent, confidence = UNCLEAR, 0.0
    if isinstance(confidence, (int, float)) and confidence < esc.confidence_threshold:
        if intent not in (SMALLTALK, OUT_OF_SCOPE):
            intent = UNCLEAR
    priority = raw.get("priority", "normal")
    lowered = masked.lower()
    # Floors the model cannot lower: anger and legal threats are always urgent, legal ones human.
    if raw.get("sentiment") == "angry":
        priority = "high"
    if any(term in lowered for term in esc.legal_terms) and "legal_threat" in manifest.intents:
        intent, priority = "legal_threat", "high"
    return {
        "intent": intent,
        "confidence": confidence,
        "sentiment": raw.get("sentiment", "neutral"),
        "priority": priority,
    }


def _actor_context(triage, facts, allowed, state, manifest, feedback):
    esc = manifest.escalation
    return {
        "triage": triage,
        "facts": facts,
        "allowed_actions": [
            {"name": a.name, "description": a.description, "params": a.params}
            for a in allowed.values()
        ],
        "pending_action": None,
        "clarifications_used": state.clarifications_used,
        "max_clarifications": esc.max_clarifications,
        "confidence_threshold": esc.confidence_threshold,
        "previous_attempt_problem": feedback,
    }


def _describe(plan: dict) -> str:
    if plan["needs_clarification"]:
        return f"питання: {plan['needs_clarification']}"
    return ", ".join(a["name"] for a in plan["actions"]) or "дій немає"


def _plan_and_gate(user, masked, triage, facts, ctx, allowed, state, manifest, trace):
    """Ask the Actor, validate, gate. Returns (plan, gate_result) or an Outcome to stop with."""
    esc = manifest.escalation
    intent, priority = triage["intent"], triage["priority"]
    feedback = None
    for _attempt in range(1 + esc.max_rejections):
        raw = router.route(
            "actor",
            {
                "context": _actor_context(triage, facts, allowed, state, manifest, feedback),
                "customer_message": masked,
            },
        )
        if raw.get("_fallback"):
            return _handoff(manifest, trace, masked, intent, priority, "actor_unavailable")
        problems = planning.validate_plan(raw, allowed, facts)
        if problems:
            feedback = "; ".join(problems)[:500]
            trace.append(trace_step("actor", "reject", feedback))
            continue
        plan = planning.strip_identity(raw)
        trace.append(trace_step("actor", "info", _describe(plan)))
        if plan["needs_clarification"]:
            if state.clarifications_used >= esc.max_clarifications:
                return _handoff(manifest, trace, masked, intent, priority, "clarification limit")
            state.clarifications_used += 1
            return Outcome("clarify", plan["needs_clarification"], trace, intent, priority)
        result = gate_plan(user.pk, masked, plan, ctx, record=False)
        trace.extend(result.trace)
        if result.decision == CLARIFY:  # Critic rejected it or nothing to do: try again
            feedback = result.reason
            continue
        return plan, result
    return _handoff(manifest, trace, masked, intent, priority, "plan rejected repeatedly")


def _execute(user, plan, facts, masked, intent, priority, manifest, trace):
    gateway = _gateway(user)
    outcomes: list[ActionOutcome] = []
    try:
        with gateway.turn("orchestrator turn") as turn:
            for action in plan["actions"]:
                outcome = gateway.run(turn, action["name"], action["params"], facts)
                outcomes.append(outcome)
                ok = outcome.status != FAILED
                trace.append(
                    trace_step(
                        "executor",
                        "done" if ok else "failed",
                        f"{action['name']}: {outcome.status}"
                        + (f" ({outcome.error})" if not ok else ""),
                    )
                )
                if not ok:
                    break
    except Busy:
        return Outcome("busy", manifest.responses["busy"], trace, intent, priority)

    for action, outcome in zip(plan["actions"], outcomes, strict=False):
        spec = manifest.actions[action["name"]]
        if outcome.status in (DONE, AWAITING) and not spec.read_only:
            policy.record(user.pk, action["name"], action["params"])
    failed = next((o for o in outcomes if o.status == FAILED), None)
    if failed:
        out = _handoff(
            manifest,
            trace,
            masked,
            intent,
            priority,
            f"execution failed: {failed.error}",
            action=failed.action,
            params=plan["actions"][len(outcomes) - 1]["params"],
        )
        out.reply = manifest.responses["failed"]
        return out
    reply = responder.polish(responder.outcome_reply(outcomes, facts, manifest), "execute", "uk")
    return Outcome("execute", reply, trace, intent, priority, reset_clarifications=True)


def _run(chat, user, text, state, manifest) -> Outcome:
    esc = manifest.escalation
    checked, step = screen_input(user.pk, text)
    trace = [step]
    if checked.verdict == BLOCK:
        return Outcome(
            "block", manifest.responses["block"], trace, "blocked", reason=checked.reason
        )
    masked = checked.masked_text

    if chat.reviews.filter(status=ReviewItem.Status.PENDING).exists():
        return Outcome(
            "review", manifest.responses["review"], trace, state.last_intent or "waiting"
        )

    try:
        facts = _gateway(user).load_facts()
    except ProductUnavailable as exc:
        reason = f"product unavailable: {exc}"
        return _handoff(manifest, trace, masked, "unknown", "normal", reason)
    ctx = product.policy_ctx(user, facts)
    triage = _triage(masked, state, manifest)
    intent, priority = triage["intent"], triage["priority"]
    trace.append(
        trace_step("triage", "info", f"{intent} · {triage['sentiment']} · пріоритет {priority}")
    )

    if intent == SMALLTALK:
        return Outcome("clarify", manifest.responses["smalltalk"], trace, intent, priority)
    if intent == OUT_OF_SCOPE:
        return Outcome("clarify", manifest.responses["out_of_scope"], trace, intent, priority)
    spec = manifest.intents.get(intent)
    if spec and spec.always_human:
        return _handoff(
            manifest, trace, masked, intent, priority, f"інтент {intent} лише для людини"
        )
    if intent == UNCLEAR:
        if state.clarifications_used >= esc.max_clarifications:
            return _handoff(manifest, trace, masked, intent, priority, "clarification limit")
        state.clarifications_used += 1
        return Outcome("clarify", manifest.responses["clarify"], trace, intent, priority)

    allowed = {a.name: a for a in manifest.allowed_actions(intent)}
    stopped = _plan_and_gate(user, masked, triage, facts, ctx, allowed, state, manifest, trace)
    if isinstance(stopped, Outcome):
        return stopped
    plan, result = stopped

    if result.decision == BLOCK:
        return Outcome("block", manifest.responses["block"], trace, intent, priority, result.reason)
    if result.decision == REVIEW:
        risky = next(
            (a for a in plan["actions"] if not manifest.actions[a["name"]].read_only), None
        )
        action = risky or {"name": "escalate_to_human", "params": {"reason": result.reason}}
        return _handoff(
            manifest,
            trace,
            masked,
            intent,
            priority,
            result.reason,
            action["name"],
            action["params"],
        )
    if result.decision != EXECUTE:  # unreachable today; refuse rather than guess
        return Outcome("block", manifest.responses["block"], trace, intent, priority)
    return _execute(user, plan, facts, masked, intent, priority, manifest, trace)


def _apply(chat: Chat, state: TurnState, outcome: Outcome) -> None:
    with transaction.atomic():
        review.add_trace(chat, outcome.trace)
        review.add_message(chat, "ai", outcome.reply)
        if outcome.priority in PRIORITY and PRIORITY[outcome.priority] != chat.priority:
            order = [Chat.Priority.LOW, Chat.Priority.NORMAL, Chat.Priority.HIGH]
            if order.index(PRIORITY[outcome.priority]) > order.index(chat.priority):
                chat.priority = PRIORITY[outcome.priority]
                chat.save(update_fields=["priority"])
        if outcome.review:
            chat.summary = outcome.summary
            chat.save(update_fields=["summary"])
            review.open_review(chat, **outcome.review)
        if outcome.reset_clarifications:
            state.clarifications_used = 0
        if outcome.intent:
            state.last_intent = outcome.intent[:60]
        state.save()


def handle_customer_message(chat: Chat, message=None, manifest: Manifest | None = None) -> Outcome:
    """Entry point from the review app: run the whole pipeline for the customer's newest message."""
    manifest = manifest or get_manifest()
    state, _ = TurnState.objects.get_or_create(chat=chat)
    if chat.customer is None:  # a chat that belongs to no account cannot be acted on
        outcome = _handoff(manifest, [], "", "unknown", "normal", "chat has no customer account")
    else:
        text = message.text if message is not None else ""
        with message_budget():
            outcome = _run(chat, chat.customer, text, state, manifest)
    _apply(chat, state, outcome)
    logger.info("orchestrator decision=%s intent=%s", outcome.decision, outcome.intent)
    return outcome


def execute_approved(customer, action: str, params: dict) -> None:
    """Run an action a human approved. Policy checks it again first, with fresh facts."""
    if action == "escalate_to_human":
        return  # the human already has the conversation
    gateway = _gateway(customer)
    try:
        facts = gateway.load_facts()
    except ProductUnavailable as exc:
        raise ExecutionError(str(exc)) from exc
    ctx = product.policy_ctx(customer, facts)
    verdict = policy.evaluate(customer.pk, action, params, ctx, mode=policy.AFTER_APPROVAL)
    if verdict.decision != policy.ALLOW:
        raise ExecutionError(verdict.reason)
    try:
        with gateway.turn("operator approved") as turn:
            outcome = gateway.run(turn, action, params, facts, reason="Approved by an operator")
    except Busy as exc:
        raise ExecutionError("Продукт зайнятий, повторіть за хвилину") from exc
    if outcome.status == FAILED:
        raise ExecutionError(outcome.error)
    policy.record(customer.pk, action, params)


def pending_confirmation(user) -> dict | None:
    """The action waiting for this customer's own confirm button, if any."""
    if settings.ORCHESTRATOR_GATEWAY == "mcp":
        from .mcp_gateway import pending_confirmation as pending_product_confirmation

        return pending_product_confirmation(user)
    from apps.support.models import Action
    from apps.support.serializers import ActionSerializer

    action = (
        Action.objects.filter(
            requesting_user=user, status="awaiting_confirmation", expires_at__gt=timezone.now()
        )
        .order_by("-created_at")
        .first()
    )
    return ActionSerializer(action).data if action else None
