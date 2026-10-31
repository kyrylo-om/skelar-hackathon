import sqlite3

import pytest
from starlette.testclient import TestClient

from mocks.cloudbox.app import create_app as cloudbox_app
from mocks.shopx.app import create_app as shopx_app

KEY = "test-key"


def client(create, tmp_path, customer: str | None = None) -> TestClient:
    app = create(db_path=tmp_path / "db.sqlite3", api_key=KEY)
    headers = {"Authorization": f"Bearer {KEY}"}
    if customer:
        headers["X-Customer-Id"] = customer
    return TestClient(app, headers=headers)


@pytest.fixture
def cloudbox(tmp_path):
    return client(cloudbox_app, tmp_path, "c-101")


@pytest.fixture
def shopx(tmp_path):
    return client(shopx_app, tmp_path, "s-201")


# Shared plumbing


@pytest.mark.parametrize(
    "create, tables",
    [
        (cloudbox_app, {"customers", "plans", "subscriptions", "payments"}),
        (shopx_app, {"customers", "orders", "order_items", "refunds"}),
    ],
)
def test_database_is_built_from_the_context_schema(create, tables, tmp_path):
    create(db_path=tmp_path / "db.sqlite3", api_key=KEY)
    db = sqlite3.connect(tmp_path / "db.sqlite3")
    found = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables <= found


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Customer-Id": "c-101"},
        {"Authorization": "Bearer wrong", "X-Customer-Id": "c-101"},
        {"Authorization": f"Bearer {KEY}"},
        {"Authorization": f"Bearer {KEY}", "X-Customer-Id": "c-999"},
    ],
)
def test_api_needs_key_and_known_customer(headers, tmp_path):
    app = cloudbox_app(db_path=tmp_path / "db.sqlite3", api_key=KEY)
    assert TestClient(app).get("/me", headers=headers).status_code == 401


def test_portal_login(tmp_path):
    portal = TestClient(cloudbox_app(db_path=tmp_path / "db.sqlite3", api_key=KEY))
    assert "<title>CloudBox</title>" in portal.get("/").text
    assert {"id": "c-101", "name": "Олена Коваль"} in portal.get("/portal/customers").json()
    assert portal.post("/portal/login", json={"customer_id": "c-999"}).status_code == 404
    assert portal.post("/portal/login", json={"customer_id": "c-101"}).status_code == 200
    assert portal.get("/me").json()["id"] == "c-101"
    portal.post("/portal/logout")
    assert portal.get("/me").status_code == 401


# CloudBox


def test_cloudbox_sync_applies_a_paid_plan_once(cloudbox):
    assert cloudbox.get("/subscription").json()["plan"] == "Free"
    response = cloudbox.post("/subscription/sync", json={"payment_id": "pay-501"})
    assert response.status_code == 200
    assert response.json()["plan"] == "Plus"
    assert response.json()["period_end"]
    again = cloudbox.post("/subscription/sync", json={"payment_id": "pay-501"})
    assert again.status_code == 409


def test_cloudbox_sync_refuses_failed_and_foreign_payments(cloudbox):
    assert cloudbox.post("/subscription/sync", json={"payment_id": "pay-500"}).status_code == 409
    assert cloudbox.post("/subscription/sync", json={"payment_id": "pay-502"}).status_code == 404


def test_cloudbox_auto_renewal(tmp_path):
    api = client(cloudbox_app, tmp_path, "c-102")
    response = api.post("/subscription/auto-renewal/off", json={})
    assert response.json()["auto_renew"] is False
    assert response.json()["plan"] == "Pro"


def test_cloudbox_refund_up_to_the_payment(tmp_path):
    api = client(cloudbox_app, tmp_path, "c-103")
    assert api.post("/payments/pay-504/refund", json={"amount": 99}).json()["refunded"] == 99
    assert api.post("/payments/pay-504/refund", json={"amount": 1}).status_code == 409
    assert api.post("/payments/pay-503/refund", json={"amount": -5}).status_code == 422


# ShopX


def test_shopx_lists_only_own_orders(shopx):
    assert {o["number"] for o in shopx.get("/orders").json()} == {"1042", "1043", "1044"}
    assert shopx.get("/orders/2001").status_code == 404
    assert shopx.post("/orders/2001/cancel", json={}).status_code == 404


def test_shopx_cancel_only_processing(shopx):
    assert shopx.post("/orders/1042/cancel", json={}).json()["status"] == "cancelled"
    assert shopx.post("/orders/1044/cancel", json={}).status_code == 409


def test_shopx_change_address(shopx):
    response = shopx.patch("/orders/1042/address", json={"address": "Одеса, вул. Дерибасівська, 3"})
    assert response.json()["address"] == "Одеса, вул. Дерибасівська, 3"
    assert shopx.patch("/orders/1044/address", json={"address": "Одеса, 1"}).status_code == 409
    assert shopx.patch("/orders/1042/address", json={"address": ""}).status_code == 422


def test_shopx_refund_only_delivered_and_up_to_total(shopx):
    response = shopx.post("/orders/1043/refund", json={"amount": 499, "reason": "розбита чашка"})
    assert response.json()["refunds"][0]["amount"] == 499
    over = shopx.post("/orders/1043/refund", json={"amount": 3000, "reason": "x"})
    assert over.status_code == 409
    assert shopx.post("/orders/1042/refund", json={"amount": 10, "reason": "x"}).status_code == 409
