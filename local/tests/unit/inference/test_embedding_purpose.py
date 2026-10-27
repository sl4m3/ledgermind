from __future__ import annotations

import pytest

from ledgermind_local.embedding_purpose import validate_embedding_purpose


def test_core_object_signature_projection_is_supported() -> None:
    assert validate_embedding_purpose("object_signature") == "object_signature"


def test_unknown_embedding_purpose_remains_rejected() -> None:
    with pytest.raises(ValueError, match="embedding purpose is not supported"):
        validate_embedding_purpose("scenario_specific_embedding")
