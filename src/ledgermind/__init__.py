import os

def _get_version():
    try:
        version_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        # Silently fallback to default version if file cannot be read
        pass
    return "3.0.0"

__version__ = _get_version()
