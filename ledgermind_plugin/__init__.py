"""
LedgerMind Plugin for Hermes Agent

Autonomous memory management for AI agents.

Two modes:
1. agent - Agent produces summaries after each round, hook captures them
2. core - LedgerMind processes raw data autonomously (local model or separate LLM)
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Global memory instance
_memory_instance = None

# Global config instance
_config = None

# Common stop words to filter out
_STOP_WORDS = {
    'what', 'is', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
    'to', 'for', 'of', 'with', 'by', 'from', 'as', 'into', 'through',
    'during', 'before', 'after', 'above', 'below', 'between', 'out', 'off',
    'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there',
    'when', 'where', 'why', 'how', 'all', 'both', 'each', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'can', 'will', 'just', 'don',
    'should', 'now', 'tell', 'me', 'about', 'do', 'you', 'know', 'can',
    'could', 'would', 'please', 'help', 'find', 'search', 'look', 'get'
}

# Default config values
DEFAULT_CONFIG = {
    "storage_path": "~/.ledgermind",
    "mode": "agent",
    "language": "russian",
    "enrichment_model": "deepseek-chat",
    "namespace": "default",
    "relevance_threshold": 0.5,
    "max_context_items": 5
}


def _clean_query(query: str) -> str:
    """Clean and normalize a query for search."""
    # Remove special characters but keep spaces
    cleaned = re.sub(r'[^\w\s]', ' ', query)
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _extract_keywords(query: str) -> List[str]:
    """Extract meaningful keywords from a query."""
    cleaned = _clean_query(query)
    words = cleaned.split()
    # Filter out stop words and short words
    keywords = [w.lower() for w in words if len(w) > 2 and w.lower() not in _STOP_WORDS]
    return keywords


def _load_config() -> Dict[str, Any]:
    """Load configuration from config file."""
    global _config
    if _config is not None:
        return _config
    
    # Try to find config file
    config_paths = [
        os.path.expanduser("~/.ledgermind/config.yaml"),
        os.path.expanduser("~/.hermes/ledgermind/config.yaml"),
        os.path.join(os.path.dirname(__file__), "config.yaml"),
    ]
    
    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                import yaml
                with open(config_path, 'r') as f:
                    _config = yaml.safe_load(f) or {}
                logger.info(f"Loaded config from {config_path}")
                return _config
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
    
    # Use defaults if no config found
    _config = DEFAULT_CONFIG.copy()
    logger.info("Using default configuration")
    return _config


def _get_config_value(key: str, default: Any = None) -> Any:
    """Get a configuration value."""
    config = _load_config()
    return config.get(key, default)


def _get_memory():
    """Get or initialize the LedgerMind memory instance."""
    global _memory_instance
    if _memory_instance is not None:
        return _memory_instance
    
    try:
        from ledgermind.core.api.memory import Memory
        
        # Get configuration
        storage_path = _get_config_value("storage_path", "~/.ledgermind")
        storage_path = os.path.expanduser(storage_path)
        
        namespace = _get_config_value("namespace", "default")
        
        _memory_instance = Memory(storage_path=storage_path, namespace=namespace)
        logger.info(f"LedgerMind initialized: {storage_path} (namespace: {namespace})")
    except Exception as e:
        logger.error(f"Failed to initialize LedgerMind: {e}")
        return None
    
    return _memory_instance


def _search_with_keywords(memory, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search using extracted keywords with fallback to individual keyword search."""
    # First try the original query
    results = memory.search_decisions(query, limit=limit, mode="lite")
    if results:
        return results
    
    # Extract keywords and search with each
    keywords = _extract_keywords(query)
    if not keywords:
        return []
    
    # Search with each keyword and combine results
    all_results = []
    seen_ids = set()
    
    for keyword in keywords:
        results = memory.search_decisions(keyword, limit=limit, mode="lite")
        for r in results:
            fid = r.get('fid') or r.get('id')
            if fid and fid not in seen_ids:
                seen_ids.add(fid)
                all_results.append(r)
    
    # Sort by score and return top results
    all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    return all_results[:limit]


def _on_pre_tool_call(tool_name: str = "", args: Any = None, **kwargs) -> Optional[Dict[str, str]]:
    """Hook called before each tool call. Injects relevant memories."""
    try:
        memory = _get_memory()
        if not memory:
            return None
        
        # Get the current prompt from args if available
        if not isinstance(args, dict):
            return None
        
        prompt = args.get("prompt") or args.get("query") or args.get("command")
        if not prompt:
            return None
        
        # Get max context items from config
        max_items = _get_config_value("max_context_items", 5)
        
        # Search for relevant memories using keyword extraction
        results = _search_with_keywords(memory, prompt, limit=max_items)
        
        if results:
            # Format context for injection
            context_items = []
            for r in results:
                item = {
                    "title": r.get("title", ""),
                    "target": r.get("target", ""),
                    "rationale": r.get("rationale", ""),
                    "score": r.get("score", 0)
                }
                context_items.append(item)
            
            context_str = f"[LEDGERMIND KNOWLEDGE BASE ACTIVE]\n{json.dumps({'source': 'ledgermind', 'memories': context_items}, indent=2, ensure_ascii=False)}"
            return {"action": "inject_context", "context": context_str}
        
        return None
        
    except Exception as e:
        logger.error(f"Error in pre_tool_call hook: {e}")
        return None


def _on_post_tool_call(tool_name: str = "", args: Any = None, result: Any = None, task_id: str = "", **kwargs) -> None:
    """Hook called after each tool call. Records the interaction."""
    try:
        memory = _get_memory()
        if not memory:
            return
        
        mode = _get_config_value("mode", "agent")
        
        # Get the user prompt from args
        if isinstance(args, dict):
            prompt = args.get("prompt") or args.get("query") or args.get("command")
        else:
            prompt = ""
        
        if not prompt:
            return
        
        if mode == "agent":
            # Agent mode: capture the summary produced by the agent
            # The result should already be a summary from the agent
            if result:
                memory.process_event(
                    source="user",
                    kind="prompt",
                    content=prompt
                )
                
                memory.process_event(
                    source="agent",
                    kind="result",
                    content=str(result)
                )
        else:
            # Core mode: record raw data for autonomous processing
            # LedgerMind will process this through its own reasoning engine
            if result:
                memory.process_event(
                    source="user",
                    kind="prompt",
                    content=prompt
                )
                
                memory.process_event(
                    source="agent",
                    kind="result",
                    content=str(result)
                )
                
                # Trigger autonomous processing in background
                # This would be handled by LedgerMind's background worker
        
    except Exception as e:
        logger.error(f"Error in post_tool_call hook: {e}")


def register(ctx) -> None:
    """Register hooks with Hermes."""
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
