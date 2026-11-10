"""Compatibility import: consumes the installed ledgermind_inference binary package."""
import sys
from ledgermind_inference import openai_vectorizer as _shared

sys.modules[__name__] = _shared
