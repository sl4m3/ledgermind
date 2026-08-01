"""Tests for source round reference domain object."""

import dataclasses
import pytest

from ledgermind_core.domain.source_reference import SourceReference


def _make_reference(message_ids: tuple[str, ...] = ()) -> SourceReference:
    return SourceReference(
        source_system="hermes",
        source_instance_id="inst_1",
        source_profile_id="profile_default",
        source_session_id="sess_1",
        source_round_id="round_1",
        first_message_id="m1",
        final_message_id="m2",
        message_ids=message_ids,
        source_digest="sha256:" + "a" * 64,
        source_schema_version=1,
        resolver_version=1,
    )


def test_required_fields_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        SourceReference(
            source_system="",
            source_instance_id="inst_1",
            source_profile_id="profile_default",
            source_session_id="sess_1",
            source_round_id="round_1",
            first_message_id=None,
            final_message_id=None,
            message_ids=(),
            source_digest="sha256:" + "a" * 64,
            source_schema_version=1,
            resolver_version=1,
        )


def test_invalid_digest_format_rejected() -> None:
    with pytest.raises(ValueError):
        SourceReference(
            source_system="hermes",
            source_instance_id="inst_1",
            source_profile_id="profile_default",
            source_session_id="sess_1",
            source_round_id="round_1",
            first_message_id=None,
            final_message_id=None,
            message_ids=(),
            source_digest="not-a-digest",
            source_schema_version=1,
            resolver_version=1,
        )


def test_schema_and_resolver_versions_must_be_at_least_one() -> None:
    with pytest.raises(ValueError):
        SourceReference(
            source_system="hermes",
            source_instance_id="inst_1",
            source_profile_id="profile_default",
            source_session_id="sess_1",
            source_round_id="round_1",
            first_message_id=None,
            final_message_id=None,
            message_ids=(),
            source_digest="sha256:" + "a" * 64,
            source_schema_version=0,
            resolver_version=1,
        )

    with pytest.raises(ValueError):
        SourceReference(
            source_system="hermes",
            source_instance_id="inst_1",
            source_profile_id="profile_default",
            source_session_id="sess_1",
            source_round_id="round_1",
            first_message_id=None,
            final_message_id=None,
            message_ids=(),
            source_digest="sha256:" + "a" * 64,
            source_schema_version=1,
            resolver_version=0,
        )


def test_empty_message_ids_is_allowed() -> None:
    reference = _make_reference()
    assert reference.message_ids == ()


def test_does_not_contain_file_system_path_field() -> None:
    reference = _make_reference()
    assert not hasattr(reference, "source_db_path")
    assert not hasattr(reference, "path")


def test_is_immutable() -> None:
    reference = _make_reference()
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference.source_round_id = "new"


def test_eq_is_value_based_and_source_round_key_deterministic() -> None:
    first = _make_reference(message_ids=("m1", "m2"))
    second = _make_reference(message_ids=("m1", "m2"))
    third = _make_reference(message_ids=("m3",))

    assert first == second
    assert first != third
    assert first.source_round_key_data == (
        "hermes",
        "inst_1",
        "profile_default",
        "sess_1",
        "round_1",
    )
