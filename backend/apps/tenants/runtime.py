"""One customer's session with one connected product, and the only ways to change it.

Reads run at once and go to the journal. A change is never made here on the model's say-so:
`prepare_write` turns a proposed change into a plan with the evidence Policy needs (what the
customer's own reads returned, which conditions hold), and `execute_write` runs it only after
Gate said so. The product is reached through the execution server alone.
"""

import time
from dataclasses import dataclass, field

from django.conf import settings

from apps.orchestrator.gateway import DONE, FAILED, ActionOutcome
from apps.security import policy

from . import client as execution
from . import journal
from .client import TenantUnavailable
from .endpoints import Endpoint, EndpointError, build_path, check_body
from .manifest import ManifestError, Tenant, build_tenant, load_rules
from .models import ApiCall, TenantCustomer
from .sanitize import sanitize

CONTEXT_TTL = 300
MAX_SEEN = 500
_context_cache: dict = {}


def action_id(tenant: str, endpoint_id: str) -> str:
    return f"{tenant}.{endpoint_id}"


def _leaves(value, found: set) -> None:
    """Every plain value in a product's answer: the ids this customer can legitimately name."""
    if len(found) >= MAX_SEEN:
        return
    if isinstance(value, dict):
        for item in value.values():
            _leaves(item, found)
    elif isinstance(value, list):
        for item in value:
            _leaves(item, found)
    elif isinstance(value, (str, int)) and not isinstance(value, bool):
        found.add(str(value))


@dataclass
class Session:
    tenant: Tenant
    user: object
    external_id: str
    client: object
    token: str = field(repr=False)  # the customer's signed token; never leaves this object
    chat: object = None
    seen: set = field(default_factory=set)  # values returned by this customer's own reads
    observations: list = field(default_factory=list)
    _cache: dict = field(default_factory=dict)

    # ---- reads ---------------------------------------------------------------------------
    def read(self, endpoint: Endpoint, path_params: dict | None = None, initiator="agent") -> dict:
        path = build_path(endpoint, path_params or {})
        if path in self._cache:
            return self._cache[path]
        with journal.timed() as elapsed:
            try:
                answer = self.client.read(self.token, path)
            except Exception as exc:  # noqa: BLE001 - any failure of the way out is "unavailable"
                journal.record(
                    tenant=self.tenant.id,
                    kind=ApiCall.READ,
                    method="GET",
                    path=path,
                    status="error",
                    duration_ms=elapsed(),
                    endpoint_id=endpoint.id,
                    response={"error": type(exc).__name__},
                    chat=self.chat,
                    customer=self.external_id,
                    initiator=initiator,
                )
                raise TenantUnavailable(f"read {path} failed") from exc
        status = answer.get("http_status")
        journal.record(
            tenant=self.tenant.id,
            kind=ApiCall.READ,
            method="GET",
            path=path,
            status=status,
            duration_ms=elapsed(),
            endpoint_id=endpoint.id,
            response=answer.get("data"),
            chat=self.chat,
            customer=self.external_id,
            initiator=initiator,
        )
        if isinstance(status, int) and status < 400:
            _leaves(answer.get("data"), self.seen)
        self._cache[path] = answer
        return answer

    def warm(self) -> None:
        """Read every list-like GET (no path variables).

        Ensures ownership can be proven from the product.
        """
        for endpoint in self.tenant.endpoints.values():
            if endpoint.kind == "read" and not endpoint.path_vars:
                try:
                    self.read(endpoint, initiator="policy")
                except TenantUnavailable:
                    continue

    # ---- the evidence for a change ---------------------------------------------------------
    def unmet_requirements(self, endpoint: Endpoint, values: dict) -> list[str]:
        """Labels of the rule's conditions that the product's own data does not confirm."""
        unmet = []
        for need in self.tenant.rule_for(endpoint).requires:
            target = self.tenant.by_key(need.read)
            holds = False
            try:
                data = self.read(target, initiator="policy").get("data")
                rows = data if isinstance(data, list) else [data]
                wanted = {k: str(v).format_map(values) for k, v in need.where.items()}
                for row in rows:
                    if isinstance(row, dict) and all(
                        str(row.get(k)) == v for k, v in wanted.items()
                    ):
                        cell = row.get(need.field)
                        holds = (cell in (None, "")) if need.empty else (cell in need.allowed)
                        break
            except (KeyError, TenantUnavailable, EndpointError):
                holds = False
            if not holds:
                unmet.append(need.label)
        return unmet

    def spec_for(self, endpoint: Endpoint) -> dict:
        rule = self.tenant.rule_for(endpoint)
        types = {name: "str" for name in endpoint.path_vars}
        for name, example in endpoint.body_example.items():
            numeric = isinstance(example, (int, float)) and not isinstance(example, bool)
            types[name] = "number" if numeric else "str"
        identifiers = [
            n for n in types if n == "id" or n.endswith("_id") or n in endpoint.path_vars
        ]
        required = list(endpoint.path_vars)
        if rule.amount_param:
            required.append(rule.amount_param)
        return {
            "risk": rule.risk,
            "types": types,
            "required": required,
            "identifiers": identifiers,
            "amount_param": rule.amount_param,
            "auto_max": rule.auto_max,
            "hard_max": rule.hard_max,
            "prefix": f"{self.tenant.id}.",
            "rate_limit": self.tenant.rules.rate_limit_per_hour,
            "idempotency_window": self.tenant.rules.idempotency_window_sec,
            "review_vip": self.tenant.rules.review_vip,
        }

    def prepare_write(self, endpoint: Endpoint, path_params: dict, body: dict, why: str = ""):
        """Validate a proposed change against the documented API and build its plan and context."""
        check_body(endpoint, body)
        build_path(endpoint, path_params)  # raises if a path variable is missing or odd
        params = {**path_params, **body}
        name = action_id(self.tenant.id, endpoint.id)
        ctx = {
            "registry": {name: self.spec_for(endpoint)},
            "verified": set(self.seen),
            "unmet": self.unmet_requirements(endpoint, params),
            "facts": {"observations": self.observations[-6:]},
            "vip": False,
        }
        plan = {
            "intent": "change",
            "actions": [{"name": name, "params": params, "reasoning": why[:300]}],
            "needs_clarification": None,
        }
        return plan, ctx

    # ---- the only place a change leaves ----------------------------------------------------
    def summary(self, endpoint: Endpoint, params: dict) -> str:
        template = self.tenant.rule_for(endpoint).summary
        try:
            return template.format_map(params) if template else f"{endpoint.method} {endpoint.path}"
        except (KeyError, ValueError):
            return f"{endpoint.method} {endpoint.path}"

    def execute_write(
        self, endpoint: Endpoint, path_params: dict, body: dict, initiator: str = "agent"
    ) -> ActionOutcome:
        """Propose, then execute, through the execution server. Call only after Gate said so."""
        path = build_path(endpoint, path_params)
        params = {**path_params, **body}
        name = action_id(self.tenant.id, endpoint.id)
        summary = self.summary(endpoint, params)
        started = time.monotonic()
        try:
            proposal = self.client.propose(self.token, endpoint.method, path, summary, body or None)
            journal.record(
                tenant=self.tenant.id,
                kind=ApiCall.PROPOSE,
                method=endpoint.method,
                path=path,
                status=proposal.get("status", ""),
                duration_ms=int((time.monotonic() - started) * 1000),
                endpoint_id=endpoint.id,
                request=body,
                response=proposal,
                chat=self.chat,
                customer=self.external_id,
                initiator=initiator,
            )
            began = time.monotonic()
            done = self.client.execute(proposal["proposal_id"])
        except Exception as exc:  # noqa: BLE001 - a broken way out means "not done"
            journal.record(
                tenant=self.tenant.id,
                kind=ApiCall.EXECUTE,
                method=endpoint.method,
                path=path,
                status="error",
                endpoint_id=endpoint.id,
                response={"error": type(exc).__name__},
                chat=self.chat,
                customer=self.external_id,
                initiator=initiator,
            )
            return ActionOutcome(name, FAILED, error="Продукт недоступний")
        result = done.get("result") or {}
        journal.record(
            tenant=self.tenant.id,
            kind=ApiCall.EXECUTE,
            method=endpoint.method,
            path=path,
            status=done.get("status", ""),
            duration_ms=int((time.monotonic() - began) * 1000),
            endpoint_id=endpoint.id,
            request=body,
            response=result,
            chat=self.chat,
            customer=self.external_id,
            initiator=initiator,
        )
        if done.get("status") != "executed":
            from apps.security.guard import mask_pii

            detail = (
                (result.get("body") or {}).get("detail")
                if isinstance(result.get("body"), dict)
                else ""
            )
            clean_error = mask_pii(str(detail or "Продукт відхилив запит"))[:200]
            return ActionOutcome(name, FAILED, error=clean_error)
        policy.record(self.user.pk, name, params)
        self._cache.clear()  # what the product says has just changed
        return ActionOutcome(
            name, DONE, facts={"summary": summary, "result": sanitize(result.get("body"))}
        )


def _load_context(tenant_id: str, token: str, api) -> str:
    cached = _context_cache.get(tenant_id)
    if cached and time.monotonic() - cached[0] < CONTEXT_TTL:
        return cached[1]
    text = api.context(token)
    _context_cache[tenant_id] = (time.monotonic(), text)
    return text


def session_for(user, chat=None) -> Session | None:
    """The user's session with their product, or None if they are not connected.

    A mapped customer whose product cannot be used raises TenantUnavailable: the caller hands the
    chat to a person instead of guessing.
    """
    mapping = TenantCustomer.objects.filter(user=user).first()
    if mapping is None:
        return None
    try:
        rules = load_rules(mapping.tenant)
        token = execution.make_token(mapping.tenant, mapping.external_id)
        api = execution.get_client()
        context = _load_context(mapping.tenant, token, api)
        tenant = build_tenant(rules, context)
    except (ManifestError, EndpointError) as exc:
        raise TenantUnavailable(str(exc)) from exc
    except TenantUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - the execution server being down is not a crash
        raise TenantUnavailable(f"{type(exc).__name__}") from exc
    return Session(tenant, user, mapping.external_id, api, token, chat)


def execute_approved(user, name: str, params: dict) -> None:
    """A person approved a change: prove it again from the product's data, then make it once."""
    from apps.review.ports import ExecutionError

    session = session_for(user)
    if session is None or "." not in name:
        raise ExecutionError("Дію не підтримує підключений продукт")
    tenant_key, endpoint_id = name.split(".", 1)
    endpoint = session.tenant.endpoint(endpoint_id)
    if tenant_key != session.tenant.id or endpoint is None or endpoint.kind != "write":
        raise ExecutionError("Невідома дія продукту")
    path_params = {k: v for k, v in params.items() if k in endpoint.path_vars}
    body = {k: v for k, v in params.items() if k not in endpoint.path_vars}
    session.warm()
    try:
        _, ctx = session.prepare_write(endpoint, path_params, body)
    except EndpointError as exc:
        raise ExecutionError(str(exc)) from exc
    verdict = policy.evaluate(user.pk, name, params, ctx, mode=policy.AFTER_APPROVAL)
    if verdict.decision != policy.ALLOW:
        raise ExecutionError(verdict.reason)
    outcome = session.execute_write(endpoint, path_params, body, initiator="operator")
    if outcome.status == FAILED:
        raise ExecutionError(outcome.error)


def enabled() -> bool:
    return bool(getattr(settings, "TENANTS_DIR", None))
