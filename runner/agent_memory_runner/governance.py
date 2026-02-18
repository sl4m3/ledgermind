import os
import logging
import re
from typing import List, Optional
from agent_memory_core.api.memory import Memory
from agent_memory_core.stores.semantic_store.loader import MemoryLoader

class GovernanceEngine:
    def __init__(self, memory_path: str):
        self.memory_path = os.path.abspath(memory_path)
        self._memory_instance = None
        self.relevance_threshold = 0.35 

    def warmup(self):
        try:
            _ = self.memory.vector.model
            return True
        except Exception:
            return False

    @property
    def memory(self):
        if self._memory_instance is None:
            self._memory_instance = Memory(storage_path=self.memory_path)
        return self._memory_instance

    def _get_file_content(self, filename: str) -> str:
        file_path = os.path.join(self.memory_path, "semantic", filename)
        if not os.path.exists(file_path): return ""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                data, body = MemoryLoader.parse(content)
                title = data.get("context", {}).get("title", "Document")
                return f"### {title}\n{body.strip()}"
        except Exception:
            return ""

    def fetch_relevant_context(self, query: str) -> str:
        try:
            results = self.memory.search_decisions(query, limit=3, mode="balanced")
            blocks = []
            
            for item in results:
                fid = item.get('id')
                score = item.get('score', 0)
                
                if score >= self.relevance_threshold:
                    content = self._get_file_content(fid)
                    if content:
                        blocks.append(content)
            
            if not blocks: return ""
            return (
                "\n[VERIFIED KNOWLEDGE BASE ACTIVE]\n" +
                "\n---\n".join(blocks) +
                "\n[END KNOWLEDGE BASE]\n"
            )
        except Exception:
            return ""

    def transform_input(self, user_data: bytes) -> bytes:
        try:
            # 1. Decode
            text = user_data.decode('utf-8', errors='ignore')
            
            # 2. explicit ANSI Strip (better than generic regex)
            # Remove ESC [ ... char
            text = re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]', ' ', text)
            # Remove ESC ] ... BEL/ST (OSC)
            text = re.sub(r'\x1b\][^\x07\x1b]*[\x07\x1b]', ' ', text)
            # Remove single ESC chars just in case
            text = text.replace('\x1b', ' ')
            
            # 3. Aggressive Strip of Non-Word chars
            clean_text = re.sub(r'[^\w\s\?\!\.\-]', ' ', text)
            
            # 4. Extract candidates
            candidates = re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9\s\?\!\.\-]{3,}', clean_text)
            
            if not candidates: 
                return b""
            
            # 5. Select best candidate
            query = candidates[-1].strip()
            
            if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', query):
                return b""
            
            if len(query) < 5: 
                return b""
            
            return self.fetch_relevant_context(query).encode('utf-8')
            
        except Exception:
            return b""
