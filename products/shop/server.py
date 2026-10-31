"""Shop MCP server: the tools the support agent gets for an online shop."""

from typing import Annotated

from pydantic import Field

from supportkit import ApiClient, Kit


def create_kit(backend) -> Kit:
    kit = Kit(
        "shop", backend, instructions="Online shop: orders, delivery, refunds. Prices in UAH."
    )

    @kit.tool()
    async def list_orders(api: ApiClient) -> list[dict]:
        """List the customer's orders with status and total."""
        return await api.get("/orders")

    @kit.tool()
    async def get_order(api: ApiClient, order_id: str) -> dict:
        """One order: items, status, total, delivery address, tracking number, refunded sum."""
        return await api.get(f"/orders/{order_id}")

    @kit.tool(confirm="Скасувати замовлення №{order_id}", per_hour=5)
    async def cancel_order(api: ApiClient, order_id: str) -> dict:
        """Cancel an order that is still processing."""
        return await api.post(f"/orders/{order_id}/cancel")

    @kit.tool(confirm="Змінити адресу доставки замовлення №{order_id} на «{address}»", per_hour=5)
    async def change_address(
        api: ApiClient, order_id: str, address: Annotated[str, Field(min_length=5, max_length=200)]
    ) -> dict:
        """Change the delivery address of an order that has not shipped yet."""
        return await api.post(f"/orders/{order_id}/address", {"address": address})

    @kit.tool(
        confirm="Повернути {amount:g} грн за замовлення №{order_id}", max_amount=1000, per_hour=3
    )
    async def refund(
        api: ApiClient,
        order_id: str,
        amount: Annotated[float, Field(gt=0)],
        reason: Annotated[str, Field(max_length=300)],
    ) -> dict:
        """Refund part or all of a delivered order, in UAH."""
        return await api.post(f"/orders/{order_id}/refund", {"amount": amount, "reason": reason})

    return kit
