"""Fake online-shop backend: orders, delivery addresses, refunds. In memory, reset on restart."""

import copy

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from supportkit.backend import body, error, mine, not_found, owned

ORDERS = {
    "1042": {
        "id": "1042",
        "customer_id": 7,
        "status": "processing",
        "items": ["Бездротова мишка Logitech M650"],
        "total": 420,
        "refunded": 0,
        "address": "Київ, вул. Хрещатик, 1, кв. 5",
    },
    "1043": {
        "id": "1043",
        "customer_id": 7,
        "status": "delivered",
        "items": ["Кавоварка Delonghi EC685"],
        "total": 1299,
        "refunded": 0,
        "address": "Київ, вул. Хрещатик, 1, кв. 5",
    },
    "1044": {
        "id": "1044",
        "customer_id": 7,
        "status": "shipped",
        "items": ["Книга «Кобзар»"],
        "total": 350,
        "refunded": 0,
        "address": "Київ, вул. Хрещатик, 1, кв. 5",
        "tracking": "59000123456789",
    },
    "2001": {
        "id": "2001",
        "customer_id": 8,
        "status": "processing",
        "items": ["Смартфон Samsung A55"],
        "total": 14999,
        "refunded": 0,
        "address": "Львів, пл. Ринок, 10",
    },
}


def create_app() -> Starlette:
    orders = copy.deepcopy(ORDERS)

    async def list_orders(request):
        return JSONResponse(mine(orders, request))

    async def get_order(request):
        order = owned(orders, request, "order_id")
        return JSONResponse(order) if order else not_found()

    async def cancel_order(request):
        order = owned(orders, request, "order_id")
        if order is None:
            return not_found()
        if order["status"] != "processing":
            return error(409, "Скасувати можна лише замовлення в обробці")
        order["status"] = "cancelled"
        return JSONResponse(order)

    async def change_address(request):
        order = owned(orders, request, "order_id")
        if order is None:
            return not_found()
        if order["status"] != "processing":
            return error(409, "Адресу можна змінити лише до відправлення")
        address = str((await body(request)).get("address", "")).strip()
        if not address:
            return error(422, "Адреса порожня")
        order["address"] = address
        return JSONResponse(order)

    async def refund(request):
        order = owned(orders, request, "order_id")
        if order is None:
            return not_found()
        if order["status"] != "delivered":
            return error(409, "Повернення можливе лише для доставленого замовлення")
        amount = (await body(request)).get("amount")
        if not isinstance(amount, (int, float)) or amount <= 0:
            return error(422, "Некоректна сума")
        if amount > order["total"] - order["refunded"]:
            return error(409, "Сума більша за залишок до повернення")
        order["refunded"] += amount
        return JSONResponse(order)

    return Starlette(
        routes=[
            Route("/orders", list_orders),
            Route("/orders/{order_id}", get_order),
            Route("/orders/{order_id}/cancel", cancel_order, methods=["POST"]),
            Route("/orders/{order_id}/address", change_address, methods=["POST"]),
            Route("/orders/{order_id}/refund", refund, methods=["POST"]),
        ]
    )
