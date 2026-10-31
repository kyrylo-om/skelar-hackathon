"""Print a customer token for manual testing: python -m execution.mint <tenant> <customer_id>"""

import sys

from .identity import sign

print(sign(sys.argv[1], sys.argv[2]))
