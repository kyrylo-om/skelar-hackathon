"""Run the execution server: python -m execution  (MCP at http://127.0.0.1:9000/mcp)."""

import os
import sys
from pathlib import Path

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings

from .products import load
from .server import create_server

PORT = 9000

missing = [
    name for name in ("EXECUTION_SECRET", "EXECUTION_SERVICE_KEY") if not os.environ.get(name)
]
if missing:
    sys.exit(f"Set {', '.join(missing)} first")
config = Path(os.environ.get("EXECUTION_PRODUCTS", Path(__file__).parent / "products.toml"))
security = TransportSecuritySettings(
    allowed_hosts=os.environ.get(
        "EXECUTION_ALLOWED_HOSTS", "127.0.0.1:*,localhost:*,[::1]:*"
    ).split(","),
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
)
app = create_server(load(config)).streamable_http_app(
    stateless_http=True, transport_security=security
)
uvicorn.run(app, host=os.environ.get("SERVICE_HOST", "127.0.0.1"), port=PORT)
