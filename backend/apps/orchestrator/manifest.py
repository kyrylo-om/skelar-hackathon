"""The product manifest: what the assistant may do for one product and how it talks about it.

A plain Python structure for now (see docs/agents/08_MANIFEST.md for the full YAML design). Policy
keeps the risk and limits of each action; the manifest says which actions each intent may use, where
their parameters come from, who confirms them and what the replies look like.
"""

from dataclasses import dataclass, field

from apps.security.policy import ACTIONS as POLICY_ACTIONS

# Intents the code handles itself, without an Actor plan.
SMALLTALK = "smalltalk"
OUT_OF_SCOPE = "out_of_scope"
UNCLEAR = "unclear"
SERVICE_INTENTS = (SMALLTALK, OUT_OF_SCOPE, UNCLEAR)


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    # parameter -> where its value must come from: "payments[].id", or "free" for plain text.
    params: dict = field(default_factory=dict)
    read_only: bool = False
    confirm: str = "none"  # none | customer | human


@dataclass(frozen=True)
class IntentSpec:
    id: str
    allowed_actions: tuple = ()
    always_human: bool = False


@dataclass(frozen=True)
class Escalation:
    max_clarifications: int = 2
    max_rejections: int = 2
    confidence_threshold: float = 0.6
    legal_terms: tuple = ("суд", "прокуратур", "lawsuit", "chargeback")
    # Explicit requests that reach a person even if the model is down or cannot classify them.
    human_terms: tuple = ("людин", "оператор", "менеджер", "спеціаліст", "human", "real person")
    refund_terms: tuple = ("поверн", "рефанд", "refund", "гроші назад")


@dataclass(frozen=True)
class Manifest:
    tenant: str
    brand: str
    language: str
    actions: dict
    intents: dict
    escalation: Escalation
    responses: dict

    def validate(self) -> None:
        for name in self.actions:
            if name not in POLICY_ACTIONS:
                raise ValueError(f"action {name!r} is not registered in Policy")
        for intent in self.intents.values():
            for name in intent.allowed_actions:
                if name not in self.actions:
                    raise ValueError(f"intent {intent.id!r} uses unknown action {name!r}")
        for key in ("review", "block", "failed", "busy", "smalltalk", "out_of_scope", "waiting"):
            if key not in self.responses:
                raise ValueError(f"missing response template {key!r}")

    def allowed_actions(self, intent: str) -> list[ActionSpec]:
        spec = self.intents.get(intent)
        return [self.actions[name] for name in spec.allowed_actions] if spec else []

    def intent_ids(self) -> list[str]:
        return list(self.intents)


CLOUDBOX = Manifest(
    tenant="cloudbox",
    brand="CloudBox",
    language="uk",
    actions={
        "get_subscription": ActionSpec(
            "get_subscription", "Read the customer's current plan and renewal", read_only=True
        ),
        "get_payments": ActionSpec("get_payments", "Read the customer's payments", read_only=True),
        "sync_subscription": ActionSpec(
            "sync_subscription",
            "Apply a paid but not yet applied payment to the subscription",
            params={"payment_id": "payments[].id"},
        ),
        "cancel_auto_renewal": ActionSpec(
            "cancel_auto_renewal",
            "Turn off automatic renewal; access stays until the end of the paid period",
            confirm="customer",
        ),
        "escalate_to_human": ActionSpec(
            "escalate_to_human",
            "Hand the conversation to a support specialist",
            params={"reason": "free"},
            confirm="human",
        ),
    },
    intents={
        "activation_issue": IntentSpec(
            "activation_issue", ("get_payments", "sync_subscription", "escalate_to_human")
        ),
        "subscription_status": IntentSpec(
            "subscription_status", ("get_subscription", "escalate_to_human")
        ),
        "cancel_renewal": IntentSpec(
            "cancel_renewal", ("cancel_auto_renewal", "escalate_to_human")
        ),
        "refund": IntentSpec("refund", ("escalate_to_human",), always_human=True),
        "double_charge": IntentSpec("double_charge", ("escalate_to_human",), always_human=True),
        # A request for a person never needs planning: it goes straight to the queue.
        "human_request": IntentSpec("human_request", ("escalate_to_human",), always_human=True),
        "info_question": IntentSpec("info_question", ("get_subscription", "escalate_to_human")),
        "plan_change": IntentSpec("plan_change", ("escalate_to_human",), always_human=True),
        "legal_threat": IntentSpec("legal_threat", ("escalate_to_human",), always_human=True),
        "account_deletion": IntentSpec(
            "account_deletion", ("escalate_to_human",), always_human=True
        ),
        "payment_method_change": IntentSpec(
            "payment_method_change", ("escalate_to_human",), always_human=True
        ),
    },
    escalation=Escalation(),
    responses={
        "review": "Передав ваш запит спеціалісту, відповімо в цьому чаті.",
        "block": (
            "Не можу виконати цей запит. Якщо потрібна допомога з вашою підпискою чи оплатою, "
            "опишіть, будь ласка, ситуацію."
        ),
        "failed": "Не вдалося завершити дію. Я вже передав запит спеціалісту.",
        "busy": "Ваш попередній запит ще обробляється. Повторіть, будь ласка, за хвилину.",
        "smalltalk": "Вітаю! Підкажіть, чим можу допомогти з підпискою чи оплатою?",
        "out_of_scope": "Допомагаю лише з підпискою та оплатою. Опишіть, будь ласка, ситуацію.",
        "clarify": "Підкажіть, будь ласка, що саме потрібно: проблема з оплатою чи з підпискою?",
        "no_payment": "Не бачу оплати, яку потрібно активувати. Передав запит спеціалісту.",
        "waiting": "Ваш запит уже у спеціаліста, він відповість у цьому чаті. Дякуємо за терпіння!",
        "sync_subscription.done": "Знайшов ваш платіж. Тариф {plan} активовано {period_end}.",
        "cancel_auto_renewal.awaiting": (
            "Щоб вимкнути автопродовження, натисніть «Підтвердити» нижче. "
            "Доступ збережеться {period_end}."
        ),
        "cancel_auto_renewal.already": (
            "Автопродовження вже вимкнено, доступ діє {period_end}. Нічого змінювати не треба."
        ),
        "get_subscription.done": (
            "Ваш тариф: {plan}. Діє: {period_end}. Автопродовження: {auto_renew}."
        ),
        "get_subscription.none": "Не бачу активної підписки. Передав запит спеціалісту.",
        "get_payments.done": "Останні оплати: {payments}.",
        "get_payments.none": "Оплат поки не бачу.",
    },
)
CLOUDBOX.validate()


def get_manifest() -> Manifest:
    return CLOUDBOX
