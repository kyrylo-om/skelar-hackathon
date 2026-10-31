"""The client our backend will use, against a real server on a local port."""

import socket
import threading
import time

import pytest
import uvicorn

from execution.client import ExecutionClient, ExecutionError
from execution.identity import sign
from execution.tests.conftest import SERVICE_KEY


@pytest.fixture
def url(server):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    app = server.streamable_http_app(stateless_http=True)
    live = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=live.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    while not live.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    live.should_exit = True
    thread.join(5)


def test_backend_flow(url):
    client = ExecutionClient(url, SERVICE_KEY)
    token = sign("cloudbox", "c-101")

    assert "CloudBox" in client.context(token)
    payments = client.read(token, "/payments")["data"]
    unapplied = next(p for p in payments if p["status"] == "successful" and not p["applied_at"])

    proposal = client.propose(
        token,
        "POST",
        "/subscription/sync",
        "Apply the Plus payment",
        {"payment_id": unapplied["id"]},
    )
    assert client.proposal(proposal["proposal_id"])["status"] == "proposed"
    assert client.read(token, "/subscription")["data"]["plan"] == "Free"

    executed = client.execute(proposal["proposal_id"])
    assert executed["status"] == "executed"
    assert client.read(token, "/subscription")["data"]["plan"] == "Plus"


def test_errors_are_raised(url):
    client = ExecutionClient(url, "wrong-key")
    with pytest.raises(ExecutionError, match="identify"):
        client.read("forged", "/me")
    with pytest.raises(ExecutionError, match="Unauthorized"):
        client.execute("anything")
