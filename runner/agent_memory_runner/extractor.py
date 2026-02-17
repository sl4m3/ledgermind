import re
import json
import logging
from typing import List, Dict, Any, Optional
from agent_memory_core.api.memory import Memory

logger = logging.getLogger("agent_memory_runner.extractor")

class MemoryExtractor:
    def __init__(self, memory_path: str):
        self.memory = Memory(storage_path=memory_path)
        self.buffer = ""
        # Improved explicit pattern to handle optional markdown blocks around JSON
        self.explicit_pattern = re.compile(r"MEMORY:\s*(?:```json)?\s*(\{.*?\})\s*(?:```)?", re.DOTALL)
        
        # Heuristic triggers
        self.heuristic_triggers = [
            r"I've decided to (.*)",
            r"We will use (.*) for (.*)",
            r"Decision: (.*)",
            r"Rule: (.*)",
            r"Constraint: (.*)"
        ]
        self.heuristic_patterns = [re.compile(p, re.IGNORECASE) for p in self.heuristic_triggers]
        self.recorded_ids = set()

    def process_chunk(self, text: str):
        self.buffer += text
        if len(self.buffer) > 20000:
            self.buffer = self.buffer[-20000:]

        self._check_explicit()

    def _check_explicit(self):
        matches = self.explicit_pattern.findall(self.buffer)
        for match in matches:
            # Simple content hash to avoid duplicate recording within same session
            match_hash = hash(match)
            if match_hash in self.recorded_ids:
                continue

            try:
                data = json.loads(match)
                self._record_fact(
                    title=data.get("title", "Observer Decision"),
                    target=data.get("target", "system"),
                    rationale=data.get("rationale", "Explicitly marked by model"),
                    consequences=data.get("consequences", [])
                )
                self.recorded_ids.add(match_hash)
            except Exception as e:
                pass # JSON might be incomplete while streaming

    def finalize_turn(self):
        self._check_heuristics()

    def _check_heuristics(self):
        # Scan for key phrases in the last 2000 characters
        recent_text = self.buffer[-2000:]
        lines = recent_text.split("\n")
        for line in lines:
            for pattern in self.heuristic_patterns:
                if pattern.search(line):
                    self._record_fact(
                        title="Automatic Insight",
                        target="heuristic_capture",
                        rationale=f"Heuristic extraction: {line.strip()}",
                        consequences=[]
                    )
                    break

    def _record_fact(self, title: str, target: str, rationale: str, consequences: List[str]):
        try:
            # We use a short timeout/lock check to not block the PTY stream
            self.memory.record_decision(
                title=title,
                target=target,
                rationale=f"[PTY-RUNNER] {rationale}",
                consequences=consequences
            )
            # visual feedback in the runner (optional, can be disabled for pure UX)
            # print(f"\n[💾 Memory Sync: {title}]")
        except Exception:
            pass
