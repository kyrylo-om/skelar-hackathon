"""Run the cloudbox mock: python -m mocks.cloudbox [--reset]  (--reset rebuilds the demo data)."""

import os
import sys

import uvicorn

from .app import DB, create_app

if "--reset" in sys.argv:
    DB.unlink(missing_ok=True)
uvicorn.run(create_app(), host=os.environ.get("SERVICE_HOST", "127.0.0.1"), port=9201)
