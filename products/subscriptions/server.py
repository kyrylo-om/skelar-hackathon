"""Subscriptions MCP server: the tools the support agent gets for a subscription service."""

from typing import Annotated

from pydantic import Field

from supportkit import ApiClient, Kit


def create_kit(backend) -> Kit:
    kit = Kit(
        "subscriptions",
        backend,
        instructions="Subscription service: plans, pauses, cancellations, invoices. Prices in UAH.",
    )

    @kit.tool()
    async def list_subscriptions(api: ApiClient) -> list[dict]:
        """List the customer's subscriptions with plan, price, status and renewal date."""
        return await api.get("/subscriptions")

    @kit.tool()
    async def get_subscription(api: ApiClient, subscription_id: str) -> dict:
        """One subscription: plan, price, status, renewal date."""
        return await api.get(f"/subscriptions/{subscription_id}")

    @kit.tool(confirm="Призупинити підписку {subscription_id} на {months} міс.", per_hour=3)
    async def pause_subscription(
        api: ApiClient, subscription_id: str, months: Annotated[int, Field(ge=1, le=3)]
    ) -> dict:
        """Pause an active subscription for 1 to 3 months; no charges while paused."""
        return await api.post(f"/subscriptions/{subscription_id}/pause", {"months": months})

    @kit.tool(confirm="Скасувати підписку {subscription_id}", per_hour=3)
    async def cancel_subscription(api: ApiClient, subscription_id: str) -> dict:
        """Cancel a subscription; it will not renew."""
        return await api.post(f"/subscriptions/{subscription_id}/cancel")

    @kit.tool()
    async def list_invoices(api: ApiClient) -> list[dict]:
        """List the customer's invoices with amount, refunded sum and date."""
        return await api.get("/invoices")

    @kit.tool(
        confirm="Повернути {amount:g} грн за рахунок {invoice_id}", max_amount=500, per_hour=3
    )
    async def refund_invoice(
        api: ApiClient,
        invoice_id: str,
        amount: Annotated[float, Field(gt=0)],
        reason: Annotated[str, Field(max_length=300)],
    ) -> dict:
        """Refund part or all of an invoice, in UAH."""
        return await api.post(
            f"/invoices/{invoice_id}/refund", {"amount": amount, "reason": reason}
        )

    return kit
