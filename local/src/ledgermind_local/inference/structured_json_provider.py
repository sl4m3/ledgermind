"""Compatibility import: consumes the installed ledgermind_inference binary package."""
import sys
from ledgermind_inference import structured_json_provider as _shared

sys.modules[__name__] = _shared
