from typing import Dict, Any

class TransitionError(Exception):
    """
    Raised when an illegal transition is attempted in the semantic store.
    """
    pass

class TransitionValidator:
    """
    Validator for enforcing semantic immutability (I1 Invariant).
    """
    # Fields that define the core meaning of a decision/event
    IMMUTABLE_FIELDS = ["target", "content", "source", "kind"]
    IMMUTABLE_CONTEXT = ["rationale", "target", "compressive_rationale"]

    @staticmethod
    def validate_update(old_data: Dict[str, Any], new_data: Dict[str, Any]):
        """
        Ensures that core semantics have not changed during an update.
        Only status and linking fields (superseded_by) should change for existing files.
        """
        old_ctx = old_data.get("context", {})
        new_ctx = new_data.get("context", {})
        
        # Check both root and context for pending/draft status
        is_pending = old_data.get("enrichment_status") == "pending" or old_ctx.get("enrichment_status") == "pending"
        is_draft = old_data.get("status") == "draft" or old_ctx.get("status") == "draft"
        
        # Minor edits (like typo correction) are allowed even in core fields
        def is_minor_diff(s1, s2):
            if not s1 or not s2: return s1 == s2
            # Very simple fuzzy check: length difference and prefix
            if abs(len(s1) - len(s2)) > 5: return False
            # Check if one contains most of the other
            common_start = 0
            for i in range(min(len(s1), len(s2), 20)):
                if s1[i] == s2[i]: common_start += 1
                else: break
            return common_start > 10

        for field in TransitionValidator.IMMUTABLE_FIELDS:
            # V7.0: Robust field extraction (check root then context)
            old_val = old_data.get(field) or old_ctx.get(field)
            new_val = new_data.get(field) or new_ctx.get(field)
            
            if old_val != new_val:
                # 1. Proposals can evolve as more evidence arrives
                if old_data.get("kind") == "proposal" or old_ctx.get("kind") == "proposal":
                    continue
                # 2. Minor typo correction in decisions
                if field == "content" and is_minor_diff(old_val, new_val):
                    continue
                # 3. Allow LLM enrichment to set 'Goal' into content field
                if field == "content" and (is_pending or is_draft):
                    continue
                # 4. Allow filling missing top-level fields (migration) - ONLY if really missing in BOTH
                if old_val is None and new_val is not None:
                    continue
                
                raise TransitionError(f"I1 Violation: Core field '{field}' is immutable. Change rejected.")

        for field in TransitionValidator.IMMUTABLE_CONTEXT:
            if old_ctx.get(field) != new_ctx.get(field):
                # Proposals are hypotheses, allow updating rationale as more evidence arrives
                if old_data.get("kind") == "proposal":
                    continue
                # Allow LLM enrichment to deeply populate all architectural fields while still in draft/pending
                if is_pending or is_draft:
                    continue
                # Allow filling if it was completely empty
                if not old_ctx.get(field):
                    continue
                raise TransitionError(f"I1 Violation: Semantic context field '{field}' is immutable. Change rejected.")
                
        # Also, check kind-specific constraints
        if old_data.get("kind") == "decision":
            if (old_data.get("status") == "superseded" or old_ctx.get("status") == "superseded") and new_data.get("status") == "active":
                raise TransitionError("I1 Violation: Cannot revert status from 'superseded' back to 'active'.")
