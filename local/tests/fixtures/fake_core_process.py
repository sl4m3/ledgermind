from __future__ import annotations

import sys
from pathlib import Path

_LOCAL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_LOCAL_ROOT / "src"))
for _index, _argument in enumerate(sys.argv[:-1]):
    if _argument == "--python-path":
        sys.path.insert(0, str(Path(sys.argv[_index + 1]).expanduser()))

from ledgermind_local.core_gateway.fake_process import main

if __name__ == "__main__":
    raise SystemExit(main())
