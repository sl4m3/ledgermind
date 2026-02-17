import re
import json
import logging
import os
from typing import List, Dict, Any, Optional
from agent_memory_core.api.memory import Memory

class MemoryExtractor:
    def __init__(self, memory_path: str):
        abs_path = os.path.abspath(memory_path)
        self.memory = Memory(storage_path=abs_path)
        self.raw_buffer = ""
        self.recorded_hashes = set()
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        
    def process_chunk(self, chunk: bytes):
        text = chunk.decode('utf-8', errors='ignore')
        for char in text:
            if char == '\r':
                self._flush_buffer()
                self.raw_buffer = "" 
            elif char == '\n':
                self._flush_buffer()
                self.raw_buffer = ""
            elif char == '\b':
                self.raw_buffer = self.raw_buffer[:-1]
            else:
                self.raw_buffer += char

    def _flush_buffer(self):
        clean_text = self.ansi_escape.sub('', self.raw_buffer).strip()
        
        # СТРОГИЕ ФИЛЬТРЫ ШУМА
        if not clean_text: return
        if "KNOWLEDGE PERSISTENCE PROTOCOL" in clean_text: return
        if "Thinking..." in clean_text: return
        if "Operational Context:" in clean_text: return
        if "Established Context:" in clean_text: return
        
        if len(clean_text) > 5:
            self._record_episodic(clean_text)

    def _record_episodic(self, text: str):
        h = hash(text)
        if h in self.recorded_hashes: return
        try:
            self.memory.process_event(
                source="system", 
                kind="task",     
                content=text,
                context={"layer": "pty_observation"}
            )
            self.recorded_hashes.add(h)
        except Exception:
            pass

    def flush(self):
        self._flush_buffer()
        try:
            self.memory.reflect() 
        except: pass
