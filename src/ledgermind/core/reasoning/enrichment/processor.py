import logging
from typing import Any, Tuple, List
from .config import EnrichmentConfig

logger = logging.getLogger("ledgermind-core.enrichment.processor")

class LogProcessor:
    """Prepares events logs for enrichment while respecting token limits."""
    
    @staticmethod
    def get_batch_logs(proposal: Any, episodic_store: Any, config: EnrichmentConfig) -> Tuple[str, List[int], List[int]]:
        """Extracts evidence within token limits and returns (text, used_ids, missing_ids)."""
        eids = getattr(proposal, 'evidence_event_ids', [])
        if not eids:
            return "No logs provided.", [], []
            
        # Target multiplier: 4 chars per token
        max_chars = int(config.max_tokens * 4)
        events = episodic_store.get_by_ids(eids)
        
        # Detect missing IDs (those present in proposal but not in store)
        found_ids = {e['id'] for e in events}
        missing_ids = [eid for eid in eids if eid not in found_ids]
        
        events.sort(key=lambda x: x.get('timestamp', ''))
        
        total_available = len(events)
        included_lines = []
        included_ids = []
        current_chars = 0
        
        fid = getattr(proposal, 'fid', 'unknown')
        
        for e in events:
            line = f"[{e['timestamp']}] {e['kind'].upper()}: {e['content']}"
            line_len = len(line) + 1
            
            # Add FIRST
            included_lines.append(line)
            included_ids.append(e['id'])
            current_chars += line_len
            
            # If we exceeded the limit, remove the LAST one (greedy maximizing)
            if current_chars > max_chars:
                if len(included_lines) > 1:
                    last_line = included_lines.pop()
                    included_ids.pop()
                    current_chars -= len(last_line) + 1
                break
            
        # Quality logging
        batch_size = len(included_ids)
        tail_size = total_available - batch_size
        tokens_est = current_chars // 4
        
        logger.info(f"--- [ITERATION START: {fid}] ---")
        if missing_ids:
            logger.warning(f"Detected {len(missing_ids)} phantom event IDs (missing from store).")
        logger.info(f"Total events in queue: {total_available}")
        logger.info(f"Batch size: {batch_size} events")
        logger.info(f"Context size: {current_chars:,} chars (~{tokens_est:,} tokens)")
        
        if tail_size > 0:
            logger.info(f"Remaining tail: {tail_size} events (will wait for next pass)")
        else:
            logger.info("This is the FINAL batch for this hypothesis.")
            
        if not included_lines and not missing_ids:
            logger.warning(f"No events could be included for {fid} due to size limits.")
            return "Logs too large to include even the first event.", [], []
            
        return "\n".join(included_lines), included_ids, missing_ids
