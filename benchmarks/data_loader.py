import json
import random
import string
from pathlib import Path

class DatasetManager:
    def __init__(self, data_dir="benchmarks/datasets"):
        self.data_dir = Path(data_dir)

    def get_synthetic_data(self, count):
        data = []
        for i in range(count):
            data.append({
                "title": f"Syn_{i}",
                "target": f"target_syn_{i}",
                "rationale": f"Synthetic rationale for {i}. " + self._rand_str(100)
            })
        return data

    def load_locomo(self):
        path = self.data_dir / "locomo/data.jsonl"
        if not path.exists(): return None
        with open(path, 'r') as f:
            raw_data = json.load(f)
            data = []
            for i, item in enumerate(raw_data[:200]):
                conversation = item.get("conversation", "")
                if isinstance(conversation, list):
                    text = "\n".join([str(m) for m in conversation])
                else:
                    text = str(conversation)
                
                if not text:
                    text = str(item.get("event_summary", "")) or str(item.get("observation", ""))
                
                if text:
                    data.append({
                        "title": f"LoCoMo_{i}",
                        "target": f"target_locomo_{i}",
                        "rationale": text[:5000]
                    })
            return data

    def load_longmemeval(self, version="s_cleaned"):
        path = self.data_dir / f"longmemeval/{version}.json"
        if not path.exists(): return None
        with open(path, 'r') as f:
            raw_data = json.load(f)
            data = []
            for i, item in enumerate(raw_data[:200]):
                sessions = item.get("haystack_sessions", [])
                if isinstance(sessions, list):
                    text = "\n".join([str(s.get("text", s)) if isinstance(s, dict) else str(s) for s in sessions])
                else:
                    text = str(sessions)
                
                if not text:
                    text = str(item.get("question", ""))
                
                if text:
                    data.append({
                        "title": f"LME_{i}",
                        "target": f"target_lme_{i}",
                        "rationale": text[:5000]
                    })
            return data

    def _rand_str(self, length):
        return "".join(random.choices(string.ascii_letters + string.digits, k=length))
