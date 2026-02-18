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

        for field in TransitionValidator.IMMUTABLE_FIELDS:
            if old_data.get(field) != new_data.get(field):
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
