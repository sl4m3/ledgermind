with open("src/ledgermind/core/stores/interfaces.py", "r") as f:
    content = f.read()

import re
if "def get_batch_by_fids" not in content:
    content = re.sub(
        r"    @abstractmethod\n    def get_by_fid\(self, fid: str\) -> Optional\[Dict\[str, Any\]\]:\n        pass\n",
        "    @abstractmethod\n    def get_by_fid(self, fid: str) -> Optional[Dict[str, Any]]:\n        pass\n\n    @abstractmethod\n    def get_batch_by_fids(self, fids: List[str]) -> List[Dict[str, Any]]:\n        pass\n",
        content
    )

with open("src/ledgermind/core/stores/interfaces.py", "w") as f:
    f.write(content)
