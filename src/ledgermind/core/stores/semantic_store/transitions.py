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
    IMMUTABLE_CONTEXT = ["rationale", "target"]

    @staticmethod
    def validate_update(old_data: Dict[str, Any], new_data: Dict[str, Any]):
        """
        Ensures that core semantics have not changed during an update.
        Only status and linking fields (superseded_by) should change for existing files.
        """
        
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
            old_val = old_data.get(field)
            new_val = new_data.get(field)
            if old_val != new_val:
                # 1. Proposals can evolve as more evidence arrives
                if old_data.get("kind") == "proposal":
                    continue
                # 2. Minor typo correction in decisions
                if field == "content" and is_minor_diff(old_val, new_val):
                    continue
                raise TransitionError(f"I1 Violation: Core field '{field}' is immutable. Change rejected.")

        old_ctx = old_data.get("context", {})
        new_ctx = new_data.get("context", {})
        
        for field in TransitionValidator.IMMUTABLE_CONTEXT:
            if old_ctx.get(field) != new_ctx.get(field):
                # Proposals are hypotheses, allow updating rationale as more evidence arrives
                if old_data.get("kind") == "proposal":
                    continue
                raise TransitionError(f"I1 Violation: Semantic context field '{field}' is immutable. Change rejected.")
                
        # Also, check kind-specific constraints
        if old_data.get("kind") == "decision":
            if old_ctx.get("status") == "superseded" and new_ctx.get("status") == "active":
                raise TransitionError("I1 Violation: Cannot revert status from 'superseded' back to 'active'.")
