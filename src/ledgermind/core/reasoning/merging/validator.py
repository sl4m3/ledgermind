from typing import Dict, Any, List, Optional

class DuplicateValidator:
    """Validator for verifying the correctness of candidate data and duplicate groups."""

    MAX_TITLE_LENGTH = 500

    @classmethod
    def validate_candidate(cls, candidate: Dict[str, Any]) -> Optional[str]:
        """Verifies the presence of required fields and constraints."""
        required_fields = ['title', 'content', 'keywords', 'target']
        for field in required_fields:
            if not candidate.get(field):
                return f"Missing required field: {field}"

        if len(candidate.get('title', '')) > cls.MAX_TITLE_LENGTH:
            return f"Title too long (max {cls.MAX_TITLE_LENGTH})"

        return None

    @staticmethod
    def validate_group(group: List[Dict[str, Any]]) -> Optional[str]:
        """Verifies the uniqueness of IDs within a group."""
        ids = [doc.get('id', doc.get('fid')) for doc in group]
        if len(ids) != len(set(ids)):
            return "Duplicate IDs in group"

        return None
