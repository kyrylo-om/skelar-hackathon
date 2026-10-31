from dataclasses import dataclass, field

# Guard
PASS = "pass"
BLOCK = "block"

# Critic
APPROVE = "approve"
REJECT = "reject"
NEEDS_HUMAN = "needs_human"

# Policy
ALLOW = "allow"
DENY = "deny"
NEEDS_REVIEW = "needs_review"

# Gate
EXECUTE = "execute"
REVIEW = "review"
CLARIFY = "clarify"


@dataclass(frozen=True)
class GuardResult:
    verdict: str  # pass | block
    reason: str = ""
    masked_text: str = ""


@dataclass(frozen=True)
class CriticResult:
    verdict: str  # approve | reject | needs_human
    reason: str = ""


@dataclass(frozen=True)
class PolicyResult:
    decision: str  # allow | deny | needs_review
    rule: str = ""
    reason: str = ""


@dataclass(frozen=True)
class GateResult:
    decision: str  # execute | review | block | clarify
    trace: list[dict] = field(default_factory=list)
    reason: str = ""


def trace_step(agent: str, verdict: str, detail: str) -> dict:
    """One line of the trace the frontend renders: guard|critic|policy|human|executor."""
    return {"agent": agent, "verdict": verdict, "detail": detail}
