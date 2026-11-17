"""Compatibility import: consumes the installed ledgermind_inference package."""

import sys

from ledgermind_inference import provider_lanes as _shared

sys.modules[__name__] = _shared
