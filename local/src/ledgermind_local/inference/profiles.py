"""Compatibility import: consumes the installed ledgermind_inference binary package."""
import sys
from ledgermind_inference import profiles as _shared

sys.modules[__name__] = _shared
