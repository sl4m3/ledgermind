"""Compatibility import: Local and Cloud use one strict transport validator."""
import sys
from ledgermind_inference import strict as _shared
sys.modules[__name__] = _shared
