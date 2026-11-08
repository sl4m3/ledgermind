from __future__ import annotations

from ledgermind_inference.profiles import InferenceProfile


def test_embed_query_batch_groups_value_and_object(monkeypatch) -> None:
    from ledgermind_local import bootstrap
    from ledgermind_local.bootstrap import LocalRuntime

    calls: list[tuple[tuple[str, ...], str | None]] = []

    class Vectorizer:
        dimension = 2
        fingerprint = "sha256:fake"

        def encode(self, texts, *, role=None):
            calls.append((tuple(texts), role))
            role_size = float(len(role or ""))
            return [[float(len(text)), role_size] for text in texts]

        def close(self) -> None:
            pass

    profile = InferenceProfile(
        profile_id="fixture",
        base_url="http://127.0.0.1:1/v1",
        model="fixture-model",
        secret_ref="fixture-secret",
    )

    class Resolver:
        def __init__(self, database_path) -> None:
            self.database_path = database_path

        def resolve_profile(self, memory_space_id, slot):
            return profile

    monkeypatch.setattr(bootstrap, "DatabaseBackedProfileResolver", Resolver)
    monkeypatch.setattr(
        bootstrap,
        "_build_runtime_vectorizer_factory",
        lambda config, priority=None: lambda: Vectorizer(),
    )

    runtime = object.__new__(LocalRuntime)
    runtime.database_path = "/tmp/fixture.db"
    runtime.config = None

    results = runtime.embed_query_batch_with_metadata("space", ["a", "bb", "ccc"])

    assert calls == [
        (("a", "bb", "ccc"), "query"),
        (("a", "bb", "ccc"), "query"),
    ]
    assert len(results) == 3
    assert [row[0] for row in results] == [
        (1.0, 5.0),
        (2.0, 5.0),
        (3.0, 5.0),
    ]
    assert [row[1] for row in results] == [
        (1.0, 5.0),
        (2.0, 5.0),
        (3.0, 5.0),
    ]
    assert {row[2] for row in results} == {"fixture-model"}
    versions = {row[3] for row in results}
    assert len(versions) == 1
    assert versions.pop().startswith("sha256:")


def test_embed_query_batch_empty_input_is_a_noop(monkeypatch) -> None:
    from ledgermind_local.bootstrap import LocalRuntime

    runtime = object.__new__(LocalRuntime)
    runtime.database_path = "/tmp/fixture.db"
    runtime.config = None

    assert runtime.embed_query_batch_with_metadata("space", []) == []
