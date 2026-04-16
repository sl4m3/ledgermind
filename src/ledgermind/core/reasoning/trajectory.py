import re
import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ledgermind.core.core.schemas import MemoryEvent, TrajectoryAtom, TrajectoryChain
from ledgermind.core.core.targets import TargetRegistry
from ledgermind.core.utils.datetime_utils import to_naive_utc

logger = logging.getLogger(__name__)

class TrajectoryBuilder:
    """
    Parses flat episodic events into structural Trajectory Chains.
    Deduces hierarchical targets based on file paths and tools used.
    """
    def __init__(self, target_registry: TargetRegistry):
        self.target_registry = target_registry
        
        # V7.0: Capture full hierarchical path including functional roots
        self.path_regex = re.compile(r'\b((?:src/|lib/|app/|tests/|ledgermind/|core/|server/|vscode/)(?:\w+/)+)[\w.-]+')

    def build_chains(self, events_dicts: List[Dict[str, Any]]) -> List[TrajectoryChain]:
        """Converts raw event dictionaries from SQLite into TrajectoryChains."""
        if not events_dicts:
            return []

        # 1. Convert to MemoryEvent objects for easier handling
        events = []
        for e in events_dicts:
            try:
                ctx = e.get('context', {})
                if isinstance(ctx, str) and ctx.strip():
                    import json
                    try: ctx = json.loads(ctx)
                    except: ctx = {}
                elif not ctx:
                    ctx = {}
                    
                ts_raw = e.get('timestamp')
                # Use to_naive_utc to ensure consistent format (UTC)
                ts = to_naive_utc(ts_raw) or datetime.now()
                
                try:
                    ev = MemoryEvent(
                        source=e.get('source', 'unknown'),
                        kind=e.get('kind', 'unknown'),
                        content=e.get('content', ''),
                        context=ctx,
                        timestamp=ts
                    )
                except Exception:
                    # FALLBACK for legacy events that might fail strict V5.0 validation
                    ev = MemoryEvent.model_construct(
                        source=e.get('source', 'unknown'),
                        kind=e.get('kind', 'unknown'),
                        content=e.get('content', ''),
                        context=ctx,
                        timestamp=ts
                    )
                
                # Store original ID in metadata for traceability
                if 'id' in e:
                    ev.metadata['event_id'] = e['id']
                events.append(ev)
            except Exception as ex:
                import sys
                print(f"DEBUG: Failed to parse event {e}: {ex}", file=sys.stderr)

        # 2. Slice into Atoms
        atoms = self._segment_atoms(events)
        
        # 3. Build Chains
        chains = self._link_atoms(atoms)
        
        # 4. Deduce Targets for Chains
        for chain in chains:
            self._deduce_target(chain)
            
        return chains

    def _segment_atoms(self, events: List[MemoryEvent]) -> List[TrajectoryAtom]:
        """Slices events into atoms based on 'user' prompts or significant time gaps."""
        atoms = []
        current_events = []
        
        for event in events:
            # Boundary condition: A user prompt starts a new atom
            if event.source == "user" and event.kind == "prompt":
                if current_events:
                    atoms.append(self._create_atom(current_events))
                    current_events = []
            
            # Boundary condition: Large time gap (> 30 mins) implies a new session/atom
            if current_events:
                gap = event.timestamp - current_events[-1].timestamp
                if gap > timedelta(minutes=30):
                    atoms.append(self._create_atom(current_events))
                    current_events = []
                    
            current_events.append(event)
            
        # Flush remaining
        if current_events:
            atoms.append(self._create_atom(current_events))
            
        return atoms

    def _create_atom(self, events: List[MemoryEvent]) -> TrajectoryAtom:
        start = events[0].timestamp
        end = events[-1].timestamp
        
        # Generate structural signature
        sig_parts = []
        for e in events:
            if e.kind == "call":
                tool = e.context.get("tool_name") if isinstance(e.context, dict) else None
                sig_parts.append(f"call:{tool}" if tool else "call")
            else:
                sig_parts.append(e.kind)
                
        # Compress repeating calls
        compressed_sig = []
        count = 1
        for i in range(len(sig_parts)):
            if i < len(sig_parts) - 1 and sig_parts[i] == sig_parts[i+1]:
                count += 1
            else:
                compressed_sig.append(f"{sig_parts[i]}({count})" if count > 1 else sig_parts[i])
                count = 1
                
        signature = " -> ".join(compressed_sig)
        
        return TrajectoryAtom(
            events=events,
            start_time=start,
            end_time=end,
            signature=signature
        )

    def _link_atoms(self, atoms: List[TrajectoryAtom]) -> List[TrajectoryChain]:
        """Groups atoms into chains. V5.4: Each atom is a chain."""
        return [TrajectoryChain(atoms=[atom]) for atom in atoms]

    def _deduce_target(self, chain: TrajectoryChain):
        """Attempts to find a hierarchical target for the chain (atom)."""
        # 1. Check explicit targets
        explicit_targets = {}
        decision_ids = {}
        
        for atom in chain.atoms:
            for ev in atom.events:
                if isinstance(ev.context, dict):
                    t = ev.context.get('target')
                    if t and t != "unknown": 
                        explicit_targets[t] = explicit_targets.get(t, 0) + 1
                    
                    did = ev.context.get('decision_id')
                    if did:
                        decision_ids[did] = decision_ids.get(did, 0) + 1
                        
        if explicit_targets:
            # ⚡ Bolt: Use O(N) max() with get() instead of O(N log N) sorted()[0]
            best_explicit = max(explicit_targets, key=explicit_targets.get)
            chain.global_target = self.target_registry.normalize(best_explicit)
            return

        # 2. Extract paths from tool calls to build hierarchical target
        paths = []
        for atom in chain.atoms:
            for ev in atom.events:
                if ev.kind in ("call", "result"):
                    matches = self.path_regex.findall(ev.content)
                    paths.extend(matches)
                    
        if paths:
            clean_paths = [p.strip('/') for p in paths]
            path_freq = {}
            for p in clean_paths:
                normalized = p
                # I3: Iterative stripping of root noise only
                roots_to_strip = ["src/", "ledgermind/", "ledgermind-knowledge/"]
                while True:
                    changed = False
                    for root in roots_to_strip:
                        if normalized.startswith(root):
                            normalized = normalized[len(root):]
                            changed = True
                    if not changed:
                        break
                
                # Keep functional roots like tests/, core/, server/ as start of target
                if "." in normalized:
                    normalized = normalized.rsplit(".", 1)[0]
                
                path_freq[normalized] = path_freq.get(normalized, 0) + 1
                    
            if path_freq:
                # ⚡ Bolt: Use O(N) max() with get() instead of O(N log N) sorted()[0]
                best_path = max(path_freq, key=path_freq.get)
                chain.global_target = self.target_registry.normalize(best_path)
                return

        # 3. Fallback to Decision ID
        if decision_ids:
            # ⚡ Bolt: Use O(N) max() with get() instead of O(N log N) sorted()[0]
            best_did = max(decision_ids, key=decision_ids.get)
            chain.global_target = f"Recovered-{best_did[:8]}"
            return
            
        # 4. Fallback default
        chain.global_target = "unknown"
