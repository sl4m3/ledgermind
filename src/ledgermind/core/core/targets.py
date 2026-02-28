import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from difflib import get_close_matches

logger = logging.getLogger(__name__)

class TargetRegistry:
    """
    Registry for canonical target names to prevent namespace fragmentation.
    Persists known targets and aliases to disk.
    """
    _cache: Dict[str, 'TargetRegistry'] = {} # storage_path -> instance

    def __new__(cls, storage_path: str):
        abs_path = os.path.abspath(storage_path)
        if abs_path not in cls._cache:
            instance = super(TargetRegistry, cls).__new__(cls)
            cls._cache[abs_path] = instance
            # Initialize the instance only once
            instance.storage_path = abs_path
            instance.file_path = os.path.join(abs_path, "targets.json")
            instance.targets = {} 
            instance.aliases = {}
            instance._load()
        return cls._cache[abs_path]

    def __init__(self, storage_path: str):
        # Initialization logic moved to __new__ to ensure it only runs once per path
        pass

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
        changed = False
        if name not in self.targets:
            self.targets[name] = {
                "description": description,
                "created_at": str(datetime.now()) # Use datetime for consistency
            }
            changed = True
        
        if aliases:
            for a in aliases:
                if self.aliases.get(a) != name:
                    self.aliases[a] = name
                    changed = True
        
        if changed:
            self._save()

    def suggest(self, query: str, limit: int = 3) -> List[str]:
        """Suggests existing targets similar to the query."""
        all_names = list(self.targets.keys())
        matches = get_close_matches(query, all_names, n=limit, cutoff=0.6)
        return matches
