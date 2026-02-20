import json
import os
import logging
from typing import List, Dict, Optional
from difflib import get_close_matches

logger = logging.getLogger(__name__)

class TargetRegistry:
    """
    Registry for canonical target names to prevent namespace fragmentation.
    Persists known targets and aliases to disk.
    """
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.file_path = os.path.join(storage_path, "targets.json")
        self.targets: Dict[str, Dict[str, Any]] = {} # name -> metadata
        self.aliases: Dict[str, str] = {} # alias -> canonical_name
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.targets = data.get("targets", {})
                    self.aliases = data.get("aliases", {})
            except Exception as e:
                logger.error(f"Failed to load target registry: {e}")

    def _save(self):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "targets": self.targets,
                    "aliases": self.aliases
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save target registry: {e}")

    def normalize(self, name: str) -> str:
        """
        Returns the canonical name for a given target input.
        1. Checks exact match.
        2. Checks aliases.
        3. Checks case-insensitive match.
        4. Returns original if no match found.
        """
        name = name.strip()
        if not name: return "unknown"
        
        # 1. Exact or Alias
        if name in self.targets: return name
        if name in self.aliases: return self.aliases[name]
        
        # 2. Case-insensitive
        lower_name = name.lower()
        for t in self.targets:
            if t.lower() == lower_name: return t
        for a, canonical in self.aliases.items():
            if a.lower() == lower_name: return canonical
            
        return name

    def register(self, name: str, description: str = "", aliases: List[str] = None):
        """Registers a new canonical target."""
        if name not in self.targets:
            self.targets[name] = {
                "description": description,
                "created_at": str(os.path.getctime(self.file_path)) if os.path.exists(self.file_path) else None
            }
        
        if aliases:
            for a in aliases:
                self.aliases[a] = name
        
        self._save()

    def suggest(self, query: str, limit: int = 3) -> List[str]:
        """Suggests existing targets similar to the query."""
        all_names = list(self.targets.keys())
        matches = get_close_matches(query, all_names, n=limit, cutoff=0.6)
        return matches
