"""Our side's rules for a connected product: manifest.yaml next to the product's own context.

The product's API comes from its context text (endpoints.py). This file holds only what the
product cannot tell us: how risky a write is, its limits, and what must be true first. The
rules are data, so a new product is a folder, not code.

    tenant: cloudbox                    # the product's key in execution/products.toml
    name: CloudBox
    policies: {rate_limit_per_hour: 5, idempotency_window_sec: 120}
    rules:
      - match: "POST /subscription/sync"
        risk: medium                    # low | medium | high
        summary: "Apply payment {payment_id} to the subscription"
        requires:
          # proven by READING the product, never by the customer's words
          - read: "GET /payments"
            where: {id: "{payment_id}"}
            field: status
            in: [successful]
      - match: "POST /payments/{payment_id}/refund"
        risk: high
        limits: {amount_param: amount, auto_max: 50, hard_max: 1000}

A write with no rule is treated as high risk and goes to a person: fail closed.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from django.conf import settings

from .endpoints import Endpoint, parse_api

RISKS = ("low", "medium", "high")
NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")


class ManifestError(ValueError):
    """The manifest is unusable. Loading it fails loudly; nothing is guessed."""


@dataclass(frozen=True)
class Requirement:
    read: str  # a GET endpoint key, like "GET /payments"
    where: dict
    field: str
    allowed: tuple | None = None
    empty: bool = False
    label: str = ""


@dataclass(frozen=True)
class Rule:
    match: str
    risk: str = "high"
    summary: str = ""
    requires: tuple = ()
    amount_param: str | None = None
    auto_max: float | None = None
    hard_max: float | None = None


@dataclass(frozen=True)
class Rules:
    tenant: str
    name: str
    rules: dict = field(default_factory=dict)  # "POST /path" -> Rule
    rate_limit_per_hour: int = 5
    idempotency_window_sec: int = 120
    review_vip: bool = True


def _requirement(raw) -> Requirement:
    if not isinstance(raw, dict) or not {"read", "where", "field"} <= set(raw):
        raise ManifestError("a requirement needs read, where and field")
    if ("in" in raw) == bool(raw.get("empty")):
        raise ManifestError("a requirement needs exactly one of `in` or `empty: true`")
    allowed = tuple(raw["in"]) if "in" in raw else None
    label = (
        raw.get("label")
        or f"{raw['field']}{' in ' + str(list(allowed)) if allowed else ' is empty'}"
    )
    return Requirement(
        raw["read"], dict(raw["where"]), raw["field"], allowed, bool(raw.get("empty")), label
    )


def _rule(raw) -> Rule:
    if not isinstance(raw, dict) or "match" not in raw:
        raise ManifestError("every rule needs `match`")
    risk = raw.get("risk", "high")
    if risk not in RISKS:
        raise ManifestError(f"{raw['match']}: risk must be one of {RISKS}")
    limits = raw.get("limits") or {}
    auto_max, hard_max = limits.get("auto_max"), limits.get("hard_max")
    if limits and not limits.get("amount_param"):
        raise ManifestError(f"{raw['match']}: limits need amount_param")
    if auto_max is not None and hard_max is not None and auto_max > hard_max:
        raise ManifestError(f"{raw['match']}: auto_max is above hard_max")
    return Rule(
        match=str(raw["match"]),
        risk=risk,
        summary=str(raw.get("summary", "")),
        requires=tuple(_requirement(r) for r in raw.get("requires") or ()),
        amount_param=limits.get("amount_param"),
        auto_max=auto_max,
        hard_max=hard_max,
    )


def parse_rules(text: str) -> Rules:
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ManifestError("the manifest must be a mapping")
    tenant = data.get("tenant")
    if not isinstance(tenant, str) or not NAME.fullmatch(tenant):
        raise ManifestError("`tenant` is required and must be a plain lowercase name")
    policies = data.get("policies") or {}
    rules = {}
    for raw in data.get("rules") or ():
        rule = _rule(raw)
        if rule.match in rules:
            raise ManifestError(f"{rule.match} is described twice")
        rules[rule.match] = rule
    return Rules(
        tenant=tenant,
        name=str(data.get("name", tenant)),
        rules=rules,
        rate_limit_per_hour=int(policies.get("rate_limit_per_hour", 5)),
        idempotency_window_sec=int(policies.get("idempotency_window_sec", 120)),
        review_vip=bool(policies.get("review_vip", True)),
    )


@dataclass(frozen=True)
class Tenant:
    """One connected product: its documented API plus our rules for it."""

    rules: Rules
    endpoints: dict  # id -> Endpoint, from the product's context
    context: str

    @property
    def id(self) -> str:
        return self.rules.tenant

    def endpoint(self, endpoint_id: str) -> Endpoint | None:
        return self.endpoints.get(endpoint_id)

    def by_key(self, key: str) -> Endpoint | None:
        return next((e for e in self.endpoints.values() if e.key == key), None)

    def rule_for(self, endpoint: Endpoint) -> Rule:
        """The rule for a write. No rule means high risk, so a person decides."""
        return self.rules.rules.get(endpoint.key) or Rule(match=endpoint.key)


def build_tenant(rules: Rules, context: str) -> Tenant:
    endpoints = parse_api(context)
    keys = {e.key for e in endpoints.values()}
    for rule in rules.rules.values():
        if rule.match not in keys:
            raise ManifestError(f"rule {rule.match!r} matches no endpoint in the product's API")
        for need in rule.requires:
            target = next((e for e in endpoints.values() if e.key == need.read), None)
            if target is None or target.kind != "read":
                raise ManifestError(
                    f"{rule.match}: requirement reads {need.read!r}, not a GET endpoint"
                )
    return Tenant(rules, endpoints, context)


def load_rules(tenant_id: str, base: Path | None = None) -> Rules:
    path = Path(base or settings.TENANTS_DIR) / tenant_id / "manifest.yaml"
    if not path.is_file():
        raise ManifestError(f"no manifest for tenant {tenant_id!r}")
    rules = parse_rules(path.read_text(encoding="utf-8"))
    if rules.tenant != tenant_id:
        raise ManifestError(f"manifest names tenant {rules.tenant!r}, expected {tenant_id!r}")
    return rules
