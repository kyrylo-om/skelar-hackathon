"""Read-only HTTP readiness probes using only the Python standard library."""

import argparse
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("url")
parser.add_argument("--status", type=int, default=200)
parser.add_argument("--service-key", action="store_true")
args = parser.parse_args()

headers = {}
if args.service_key:
    headers["Authorization"] = f"Bearer {os.environ['EXECUTION_SERVICE_KEY']}"
try:
    with urlopen(Request(args.url, headers=headers), timeout=3) as response:
        status = response.status
except HTTPError as exc:
    status = exc.code
raise SystemExit(0 if status == args.status else 1)
