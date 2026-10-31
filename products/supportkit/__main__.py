"""Print a customer token for manual testing: SUPPORTKIT_SECRET=... python -m supportkit 7"""

import sys

from .identity import sign

print(sign(int(sys.argv[1])))
