"""Test stand-in for the execution server running real mock Starlette apps."""

import sys
from pathlib import Path
from unittest import mock

# Ensure repo root is on sys.path so mocks can be imported
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mocks.cloudbox.app import create_app as create_cloudbox_app  # noqa: E402
from mocks.shopx.app import create_app as create_shopx_app  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

API_KEY = "test-execution-key"


class FakeExecutionClient:
    """Simulates ExecutionClient over in-process Starlette mock apps without MCP."""

    def __init__(self, apps: dict[str, object], contexts: dict[str, str]):
        self.apps = apps
        self.contexts = contexts
        self.proposals: dict[str, dict] = {}
        self._seq = 1000

    def _split_token(self, token: str) -> tuple[str, str]:
        parts = token.split(".")
        return parts[0], parts[1]

    def context(self, token: str) -> str:
        tenant, _ = self._split_token(token)
        return self.contexts.get(tenant, "")

    def read(self, token: str, path: str) -> dict:
        tenant, customer = self._split_token(token)
        app = self.apps[tenant]
        client = TestClient(
            app, headers={"Authorization": f"Bearer {API_KEY}", "X-Customer-Id": customer}
        )
        resp = client.get(path)
        data = None
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return {"http_status": resp.status_code, "data": data}

    def propose(
        self, token: str, method: str, path: str, summary: str, body: dict | None = None
    ) -> dict:
        tenant, customer = self._split_token(token)
        self._seq += 1
        pid = f"prop-{self._seq}"
        self.proposals[pid] = {
            "proposal_id": pid,
            "status": "pending",
            "tenant": tenant,
            "customer": customer,
            "method": method.upper(),
            "path": path,
            "summary": summary,
            "body": body or {},
            "executed": False,
        }
        return {"proposal_id": pid, "status": "pending"}

    def proposal(self, proposal_id: str) -> dict:
        return self.proposals.get(proposal_id, {})

    def execute(self, proposal_id: str) -> dict:
        prop = self.proposals.get(proposal_id)
        if not prop:
            return {
                "status": "failed",
                "result": {"http_status": 404, "body": {"detail": "Not found"}},
            }
        if prop["executed"]:
            return {
                "status": "failed",
                "result": {"http_status": 409, "body": {"detail": "Already executed"}},
            }
        prop["executed"] = True
        tenant, customer = prop["tenant"], prop["customer"]
        app = self.apps[tenant]
        client = TestClient(
            app, headers={"Authorization": f"Bearer {API_KEY}", "X-Customer-Id": customer}
        )
        method = prop["method"]
        body = prop["body"]
        if method == "POST":
            resp = client.post(prop["path"], json=body)
        elif method == "PATCH":
            resp = client.patch(prop["path"], json=body)
        elif method == "PUT":
            resp = client.put(prop["path"], json=body)
        elif method == "DELETE":
            resp = client.delete(prop["path"])
        else:
            resp = client.get(prop["path"])

        data = None
        try:
            data = resp.json()
        except Exception:
            data = resp.text

        status = "executed" if resp.status_code < 400 else "failed"
        return {
            "status": status,
            "result": {"http_status": resp.status_code, "body": data},
        }

    def reject(self, proposal_id: str) -> dict:
        prop = self.proposals.get(proposal_id)
        if prop:
            prop["status"] = "rejected"
        return {"status": "rejected"}


def make_fake_client(tmp_path: Path) -> FakeExecutionClient:
    cb_app = create_cloudbox_app(db_path=tmp_path / "cloudbox.sqlite3", api_key=API_KEY)
    sx_app = create_shopx_app(db_path=tmp_path / "shopx.sqlite3", api_key=API_KEY)
    repo_root = Path(__file__).resolve().parents[4]
    cb_ctx = (repo_root / "mocks" / "cloudbox" / "context.md").read_text(encoding="utf-8")
    sx_ctx = (repo_root / "mocks" / "shopx" / "context.md").read_text(encoding="utf-8")

    return FakeExecutionClient(
        apps={"cloudbox": cb_app, "shopx": sx_app},
        contexts={"cloudbox": cb_ctx, "shopx": sx_ctx},
    )


def patch_execution(fake_client: FakeExecutionClient):
    """Patch apps.tenants.runtime.execution to return the fake client and tokens."""

    def fake_make_token(tenant: str, customer_id: str) -> str:
        return f"{tenant}.{customer_id}.fake-token"

    p1 = mock.patch("apps.tenants.runtime.execution.get_client", return_value=fake_client)
    p2 = mock.patch("apps.tenants.runtime.execution.make_token", side_effect=fake_make_token)
    return p1, p2
