from supportkit import run

from .api import create_app
from .server import create_kit

API_PORT, MCP_PORT = 9102, 9002

run(create_kit(f"http://127.0.0.1:{API_PORT}"), create_app(), api_port=API_PORT, mcp_port=MCP_PORT)
