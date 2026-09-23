from __future__ import annotations

import base64
import importlib
import io
import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ledgermind_local.installer import cli, wizard
from ledgermind_local.installer.config_writer import (
    load_installer_config,
    write_installer_config,
)
from ledgermind_local.installer.errors import ProviderProbeError, UserCancelledError
from ledgermind_local.installer.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
    IntegrationConfig,
    RerankerApiConfig,
    RerankerConfig,
)
from ledgermind_local.installer.models import (
    LocalEmbeddingConfig as InstallerLocalEmbeddingConfig,
)
from ledgermind_local.installer.operations.common import unpack_bundle
from ledgermind_local.installer.operations.integrations import (
    connect_integration,
    disconnect_integration,
    set_integration_enabled,
)
from ledgermind_local.installer.operations.uninstall import uninstall
from ledgermind_local.installer.paths import InstallerPaths
from ledgermind_local.installer.targets import registry
from ledgermind_local.installer.targets.base import BaseTargetAdapter, TargetDiscovery


def _config() -> InstallerConfig:
    return InstallerConfig(
        semantic_language="en",
        generation=GenerationConfig(
            endpoint="https://provider.example/v1",
            token="generation-secret",
            model="generation",
        ),
        embedding=EmbeddingConfig(
            mode="api",
            api=EmbeddingApiConfig(
                endpoint="https://provider.example/v1",
                token="embedding-secret",
                model="embedding",
                dimensions=3,
            ),
        ),
    )


def test_installer_projects_explicit_local_reranker_without_enabling_legacy_installs(
    tmp_path: Path,
) -> None:
    from ledgermind_local.installer.config_writer import build_local_config
    from ledgermind_local.installer.models import RerankerConfig

    paths = InstallerPaths(home_override=tmp_path)
    assert not build_local_config(_config(), paths).reranker.enabled
    configured = _config().model_copy(
        update={
            "reranker": RerankerConfig(
                enabled=True,
                model_path="/models/pinned/snapshots/revision",
                runtime_path="/runtime/pinned",
                device="cpu",
            )
        }
    )
    local = build_local_config(configured, paths)
    assert local.reranker.enabled
    assert local.reranker.model_path == "/models/pinned/snapshots/revision"
    assert local.reranker.runtime_path == "/runtime/pinned"
    assert local.reranker.min_k == 6
    assert local.reranker.soft_budget == 400


def test_installer_projects_api_reranker_without_persisting_token(
    tmp_path: Path,
) -> None:
    from ledgermind_local.installer.config_writer import build_local_config

    paths = InstallerPaths(home_override=tmp_path)
    configured = _config().model_copy(
        update={
            "reranker": RerankerConfig(
                mode="api",
                api=RerankerApiConfig(
                    endpoint="https://reranker.example/v1/rerank",
                    token="reranker-secret",
                    model="rerank-model",
                ),
            )
        }
    )
    write_installer_config(configured, paths)

    persisted = paths.config_file.read_text(encoding="utf-8")
    local = build_local_config(configured, paths)
    assert "reranker-secret" not in persisted
    assert local.reranker.mode == "api"
    assert local.reranker.endpoint == "https://reranker.example/v1/rerank"
    assert local.reranker.model == "rerank-model"
    assert local.reranker.secret_ref == "reranker-api"


def test_installer_projects_local_embedding_service_credential(tmp_path: Path) -> None:
    from ledgermind_local.installer.config_writer import build_local_config

    paths = InstallerPaths(home_override=tmp_path)
    configured = _config().model_copy(
        update={
            "embedding": EmbeddingConfig(
                mode="local",
                local=InstallerLocalEmbeddingConfig(
                    catalog_id="nemotron",
                    device="cpu",
                    model_storage_path="/models/nemotron",
                    runtime_id="sentence-transformers-nemotron",
                    runtime_path="/runtime/nemotron",
                    dimensions=2048,
                ),
            )
        }
    )

    local = build_local_config(configured, paths)

    assert local.embedding.provider_mode == "api"
    assert local.embedding.endpoint == "http://127.0.0.1:8766"
    assert local.embedding.model == "nemotron"
    assert local.embedding.secret_ref == "embedding-local"


def test_legacy_target_migrates_to_current_integration() -> None:
    payload = _config().model_dump(mode="json")
    payload["schema_version"] = 1
    payload["target"] = "hermes"
    payload.pop("integrations", None)

    migrated = InstallerConfig.model_validate(payload)

    assert migrated.schema_version == 2
    assert [(item.id, item.enabled) for item in migrated.integrations] == [
        ("hermes", True)
    ]


def test_new_config_does_not_connect_an_agent_implicitly() -> None:
    assert _config().schema_version == 2
    assert _config().integrations == ()
    assert _config().memory_mode == "per_agent"


def test_memory_mode_resolves_shared_or_per_agent_spaces() -> None:
    config = _config()
    assert config.memory_space_id_for("hermes") == "hermes-default"
    assert config.memory_space_id_for("codex") == "codex-default"

    shared = config.model_copy(update={"memory_mode": "shared"})
    assert shared.memory_space_id_for("hermes") == "shared-default"
    assert shared.memory_space_id_for("codex") == "shared-default"


def test_semantic_language_accepts_and_canonicalizes_custom_bcp47_tag() -> None:
    assert (
        _config().model_copy(update={"semantic_language": "en"}).semantic_language
        == "en"
    )
    payload = _config().model_dump(mode="json")
    payload["semantic_language"] = "zh_hans"

    assert InstallerConfig.model_validate(payload).semantic_language == "zh-Hans"


def test_generation_rejects_different_legacy_semantic_models() -> None:
    with pytest.raises(ValueError, match="one model"):
        GenerationConfig(
            endpoint="https://provider.example/v1",
            token="secret",
            model="one",
            object_resolution_model="another",
        )


def test_operation_urls_are_normalized_to_openai_api_base() -> None:
    generation = GenerationConfig(
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        token="secret",
        model="model",
        route="provider/fp8",
    )
    embedding = EmbeddingApiConfig(
        endpoint="https://openrouter.ai/api/v1/embeddings",
        token="secret",
        model="embedding",
        dimensions=3,
    )

    assert generation.endpoint == "https://openrouter.ai/api/v1"
    assert embedding.endpoint == "https://openrouter.ai/api/v1"


def test_terminal_wizard_uses_reference_openrouter_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _DetectedAdapter:
        label = "Codex CLI"

        @staticmethod
        def discover() -> TargetDiscovery:
            return TargetDiscovery("codex", "Codex CLI", True, home=Path("/tmp/codex"))

    monkeypatch.setattr(registry, "target_ids", lambda: ("codex",))
    monkeypatch.setattr(
        registry, "get_target_adapter", lambda _target: _DetectedAdapter()
    )
    answers = iter(
        (
            "",  # English
            "",  # all detected agents
            "2",  # shared memory
            "",  # OpenRouter
            "",  # reference generation model
            "",  # choose discovered routes
            "2",  # primary + fallback
            "",  # Baidu primary
            "",  # DeepInfra fallback
            "",  # API embeddings
            "",  # same API base
            "",  # reuse token
            "",  # reference embedding model
            "",  # keep Core ranking; reranker is opt-in
            "",  # session model residency
            "",  # install
        )
    )
    output = io.StringIO()

    config = wizard.build_interactive_config(
        input_fn=lambda _prompt: next(answers),
        secret_fn=lambda _prompt: "secret",
        output=output,
        openrouter_endpoint_loader=lambda _model, _token: (
            wizard.OpenRouterEndpoint(
                route="baidu/fp8",
                provider="Baidu",
                quantization="FP8",
                context_length=163840,
                prompt_price=None,
                completion_price=None,
                supported_parameters=("response_format", "structured_outputs"),
            ),
            wizard.OpenRouterEndpoint(
                route="deepinfra/fp8",
                provider="DeepInfra",
                quantization="FP8",
                context_length=163840,
                prompt_price=None,
                completion_price=None,
                supported_parameters=("response_format", "structured_outputs"),
            ),
        ),
        embedding_dimension_loader=lambda _config, _token: 2048,
    )

    assert config.semantic_language == "en"
    assert config.generation.endpoint == "https://openrouter.ai/api/v1"
    assert config.generation.route == "baidu/fp8"
    assert config.generation.fallback_routes == ("deepinfra/fp8",)
    assert config.runtime.residency_mode == "session"
    assert config.runtime.session_safety_ttl_seconds == 3_600.0
    assert config.generation.model == wizard.REFERENCE_GENERATION_MODEL
    assert config.embedding.api is not None
    assert config.embedding.api.endpoint == "https://openrouter.ai/api/v1"
    assert config.embedding.api.model == "nvidia/nemotron-3-embed-1b:free"
    assert config.embedding.api.dimensions == 2048
    assert config.memory_mode == "shared"
    assert [item.id for item in config.integrations] == ["codex"]
    assert "LEDGERMIND SETUP" in output.getvalue()
    assert "REVIEW" in output.getvalue()
    assert "Token accepted:" in output.getvalue()
    assert "secret" not in output.getvalue()
    assert "baidu/fp8 → deepinfra/fp8 (restricted)" in output.getvalue()


def test_navigation_menu_keeps_rows_aligned_and_q_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStdin:
        @staticmethod
        def fileno() -> int:
            return 41

        @staticmethod
        def isatty() -> bool:
            return True

    output = io.StringIO()
    terminal = wizard._TerminalWizard(
        input_fn=input,
        secret_fn=lambda _prompt: "secret",
        output=output,
    )
    terminal.color = False
    terminal.navigation = True
    monkeypatch.setattr(wizard.sys, "stdin", _FakeStdin())
    monkeypatch.setattr(wizard.termios, "tcgetattr", lambda _descriptor: [])
    monkeypatch.setattr(wizard.termios, "tcsetattr", lambda *_arguments: None)
    monkeypatch.setattr(wizard.tty, "setraw", lambda _descriptor: None)
    monkeypatch.setattr(wizard.os, "read", lambda _descriptor, _size: b"q")

    with pytest.raises(UserCancelledError, match="cancelled"):
        terminal.choose(
            "Choose a semantic language",
            (wizard._Choice("en", "English"), wizard._Choice("es", "Spanish")),
        )

    rendered = output.getvalue()
    assert "\r\033[2K  ╭ Choose a semantic language " in rendered
    assert "\r\033[2K  │  › English" in rendered
    assert "\r\033[2K  ╰" in rendered
    assert "Esc/Q cancel" in rendered


def test_bare_escape_is_bounded_and_line_mode_has_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wizard.select, "select", lambda *_arguments: ((), (), ()))
    assert wizard._TerminalWizard._escape_tail(41) == b""

    terminal = wizard._TerminalWizard(
        input_fn=lambda _prompt: ":q",
        secret_fn=lambda _prompt: "secret",
        output=io.StringIO(),
    )
    with pytest.raises(UserCancelledError, match="cancelled"):
        terminal.ask("Model")


def test_interactive_cancellation_is_not_reported_as_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_config",
        lambda _args: (_ for _ in ()).throw(
            UserCancelledError("installation cancelled by user")
        ),
    )

    exit_code = cli.main(("install", "--home", str(tmp_path / "home")))

    captured = capsys.readouterr()
    assert exit_code == 15
    assert "install: cancelled (exit_code=15)" in captured.out
    assert "failed" not in captured.out
    assert "error:" not in captured.err


def test_bootstrap_reports_large_installer_download_progress() -> None:
    bootstrap = Path("scripts/install.sh").read_text(encoding="utf-8")

    assert "download_with_status" in bootstrap
    assert "Preparing secure download" in bootstrap
    assert "content-length:" in bootstrap
    assert "[============================]" in bootstrap
    assert "100%%" in bootstrap
    assert "--progress-bar" not in bootstrap


def test_terminal_wizard_offers_local_embedding_only_from_signed_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "target_ids", lambda: ())
    answers = iter(
        (
            "",  # English
            "",  # per-agent memory
            "3",  # custom generation endpoint
            "https://provider.example/v1",
            "generation-model",
            "2",  # local embeddings
            "",  # automatic device
            "",  # keep Core ranking; reranker is opt-in
            "",  # session model residency
            "",  # install
        )
    )

    config = wizard.build_interactive_config(
        input_fn=lambda _prompt: next(answers),
        secret_fn=lambda _prompt: "secret",
        output=io.StringIO(),
        embedding_catalog=(
            {
                "id": wizard.REFERENCE_LOCAL_EMBEDDING_CATALOG_ID,
                "devices": ["cpu", "cuda", "rocm"],
            },
        ),
    )

    assert config.embedding.mode == "local"
    assert config.embedding.local is not None
    assert (
        config.embedding.local.catalog_id == wizard.REFERENCE_LOCAL_EMBEDDING_CATALOG_ID
    )


def test_install_fails_provider_preflight_before_release_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_module = importlib.import_module(
        "ledgermind_local.installer.operations.install"
    )
    fetched = False

    def fail_probe(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ProviderProbeError("configured generation model is unavailable")

    def unexpected_fetch(*_args: Any, **_kwargs: Any) -> tuple[Path, Path, Path]:
        nonlocal fetched
        fetched = True
        raise AssertionError("release download must not start")

    manifest_path = tmp_path / "install-manifest.json"
    signature_path = tmp_path / "install-manifest.sig"
    manifest_path.write_text("{}", encoding="utf-8")
    signature_path.write_bytes(b"signature")
    manifest = SimpleNamespace()
    monkeypatch.setattr(install_module, "probe_generation", fail_probe)
    monkeypatch.setattr(
        install_module,
        "fetch_manifest",
        lambda *_args, **_kwargs: (manifest_path, signature_path, manifest),
    )
    monkeypatch.setattr(
        install_module, "verify_manifest_signature", lambda *_args: None
    )
    monkeypatch.setattr(
        install_module,
        "platform_manifest",
        lambda _manifest: SimpleNamespace(
            bundle=SimpleNamespace(size=0, minimum_glibc=None)
        ),
    )
    monkeypatch.setattr(
        install_module,
        "check_preflight",
        lambda *_args, **_kwargs: {"platform": "linux-x86_64"},
    )
    monkeypatch.setattr(install_module, "fetch_bundle", unexpected_fetch)

    with pytest.raises(ProviderProbeError, match="unavailable"):
        install_module.install(
            config=_config(), paths=InstallerPaths(home_override=tmp_path)
        )

    assert fetched is False


def test_python_312_compatible_zstandard_bundle_unpack(tmp_path: Path) -> None:
    import zstandard

    source = tmp_path / "source"
    source.mkdir()
    (source / "marker.txt").write_text("bundle", encoding="utf-8")
    tar_path = tmp_path / "bundle.tar"
    with tarfile.open(tar_path, "w") as archive:
        archive.add(source, arcname="bundle")
    archive_path = tmp_path / "bundle.tar.zst"
    archive_path.write_bytes(zstandard.ZstdCompressor().compress(tar_path.read_bytes()))

    unpacked = unpack_bundle(archive_path, tmp_path / "unpacked")

    assert (unpacked / "marker.txt").read_text(encoding="utf-8") == "bundle"


def test_bundle_unpack_removes_files_left_by_previous_release(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "current.txt").write_text("current", encoding="utf-8")
    archive_path = tmp_path / "bundle.tar"
    with tarfile.open(archive_path, "w") as archive:
        archive.add(source, arcname="bundle")

    destination = tmp_path / "unpacked"
    stale = destination / "bundle" / "python" / "local" / "src"
    stale.mkdir(parents=True)
    (stale / "old.py").write_text("stale", encoding="utf-8")

    unpacked = unpack_bundle(archive_path, destination)

    assert (unpacked / "current.txt").read_text(encoding="utf-8") == "current"
    assert not (destination / "bundle" / "python").exists()


def test_non_interactive_stdin_tokens_reach_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _config().model_dump(mode="json")
    payload["generation"].pop("token")
    payload["generation"]["token_stdin"] = True
    payload["embedding"]["api"].pop("token")
    payload["embedding"]["api"]["token_stdin"] = True
    source = tmp_path / "install.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(source, 0o600)
    captured: dict[str, Any] = {}

    def fake_install(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(cli, "install", fake_install)
    monkeypatch.setattr(
        cli.sys, "stdin", io.StringIO("generation-stdin\nembedding-stdin\n")
    )

    exit_code = cli.main(
        [
            "install",
            "--home",
            str(tmp_path / "install-home"),
            "--non-interactive",
            "--config",
            str(source),
            "--json",
        ]
    )

    assert exit_code == 0
    assert captured["generation_stdin"] == "generation-stdin"
    assert captured["embedding_stdin"] == "embedding-stdin"


def test_no_arguments_starts_the_interactive_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_install(**kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        assert kwargs["config"].semantic_language == "en"
        return {"status": "success"}

    monkeypatch.setattr(wizard, "build_interactive_config", lambda **_kwargs: _config())
    monkeypatch.setattr(cli, "install", fake_install)
    monkeypatch.setattr(
        cli,
        "_paths",
        lambda _args: InstallerPaths(home_override=tmp_path / "install-home"),
    )

    assert cli.main([]) == 0
    assert called is True


def test_repeated_install_adds_agent_without_reinstalling_or_reconfiguring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path / "install-home")
    write_installer_config(_config(), paths)
    connected: list[str] = []

    def fake_connect(**kwargs: Any) -> dict[str, Any]:
        connected.append(str(kwargs["target_id"]))
        return {"status": "passed", "connected": True}

    monkeypatch.setattr(cli, "connect_integration", fake_connect)
    monkeypatch.setattr(
        cli,
        "install",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("existing install must not download or reinstall")
        ),
    )

    exit_code = cli.main(
        [
            "install",
            "--home",
            str(tmp_path / "install-home"),
            "--existing-mode",
            "add-agent",
            "--agent",
            "hermes",
            "--json",
        ]
    )

    assert exit_code == 0
    assert connected == ["hermes"]


def test_update_uses_installed_provider_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path / "install-home")
    expected = _config()
    write_installer_config(expected, paths)
    installed = load_installer_config(paths.config_file)
    captured: dict[str, Any] = {}

    def fake_update(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(cli, "update", fake_update)

    exit_code = cli.main(
        [
            "update",
            "--home",
            str(tmp_path / "install-home"),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--bundle",
            str(tmp_path / "bundle.tar.zst"),
            "--json",
        ]
    )

    assert exit_code == 0
    assert captured["config"] == installed
    assert captured["generation_stdin"] is None
    assert captured["embedding_stdin"] is None


def test_failed_update_restores_local_database_and_skips_duplicate_provider_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_module = importlib.import_module(
        "ledgermind_local.installer.operations.update"
    )
    paths = InstallerPaths(home_override=tmp_path / "install-home")
    paths.ensure()
    previous_release = paths.release_dir("previous")
    previous_release.mkdir()
    paths.current_link.symlink_to(previous_release)
    database = paths.memory_data_dir / "rounds.db"
    database.write_bytes(b"original-database")

    def fake_install(**_kwargs: Any) -> dict[str, Any]:
        database.write_bytes(b"partially-upgraded-database")
        return {"status": "success", "release_version": "candidate"}

    def failing_doctor(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["probe_providers"] is False
        return {"status": "failed"}

    monkeypatch.setattr(update_module, "install", fake_install)
    monkeypatch.setattr(update_module, "doctor", failing_doctor)

    with pytest.raises(RuntimeError, match="previous release was retained"):
        update_module.update(
            config=_config(),
            paths=paths,
            manifest_path=tmp_path / "manifest.json",
            bundle=tmp_path / "bundle.tar.zst",
            skip_provider_probe=True,
        )

    assert paths.current_link.resolve() == previous_release
    assert database.read_bytes() == b"original-database"


def test_update_never_authorizes_install_to_rewrite_provider_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_module = importlib.import_module(
        "ledgermind_local.installer.operations.update"
    )
    paths = InstallerPaths(home_override=tmp_path / "install-home")
    paths.ensure()
    previous_release = paths.release_dir("previous")
    previous_release.mkdir()
    paths.current_link.symlink_to(previous_release)
    captured: dict[str, Any] = {}

    def fake_install(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "success", "release_version": "candidate"}

    monkeypatch.setattr(update_module, "install", fake_install)
    monkeypatch.setattr(
        update_module,
        "doctor",
        lambda **_kwargs: {"status": "passed"},
    )
    monkeypatch.setattr(
        update_module,
        "_assert_generation_capabilities_ready",
        lambda _database: None,
    )

    result = update_module.update(
        config=_config(),
        paths=paths,
        manifest_path=tmp_path / "manifest.json",
        bundle=tmp_path / "bundle.tar.zst",
        skip_provider_probe=True,
    )

    assert result["status"] == "success"
    assert captured["preserve_provider_credentials"] is True


def test_update_rolls_back_when_skipped_probe_left_generation_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_module = importlib.import_module(
        "ledgermind_local.installer.operations.update"
    )
    paths = InstallerPaths(home_override=tmp_path / "install-home")
    paths.ensure()
    previous_release = paths.release_dir("previous")
    previous_release.mkdir()
    paths.current_link.symlink_to(previous_release)
    database = paths.memory_data_dir / "rounds.db"
    database.write_bytes(b"verified-before-update")

    def fake_install(**_kwargs: Any) -> dict[str, Any]:
        database.write_bytes(b"unverified-after-update")
        return {"status": "success", "release_version": "candidate"}

    def reject_unverified(_database: Path) -> None:
        raise RuntimeError("provider probe is required")

    monkeypatch.setattr(update_module, "install", fake_install)
    monkeypatch.setattr(
        update_module, "_assert_generation_capabilities_ready", reject_unverified
    )

    with pytest.raises(RuntimeError, match="previous release was retained"):
        update_module.update(
            config=_config(),
            paths=paths,
            manifest_path=tmp_path / "manifest.json",
            bundle=tmp_path / "bundle.tar.zst",
            skip_provider_probe=True,
        )

    assert paths.current_link.resolve() == previous_release
    assert database.read_bytes() == b"verified-before-update"


def test_repair_is_local_and_does_not_probe_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repair_module = importlib.import_module(
        "ledgermind_local.installer.operations.repair"
    )
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path / "install-home")
    paths.ensure()
    release = paths.release_dir("candidate")
    (release / "bin").mkdir(parents=True)
    paths.current_link.symlink_to(release)
    write_installer_config(_config(), paths)
    monkeypatch.setattr(repair_module, "install_bin_link", lambda _paths: None)

    def fake_doctor(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["probe_providers"] is False
        return {
            "status": "passed",
            "platform": "linux-x86_64",
            "providers": {"status": "skipped_by_request"},
            "smoke_test": {"status": "passed"},
        }

    monkeypatch.setattr(repair_module, "doctor", fake_doctor)

    result = repair_module.repair(paths=paths)

    assert result["status"] == "passed"
    assert result["readiness"]["generation"] == "preserved-not-probed"


def test_provider_reconfiguration_preserves_memory_and_agents() -> None:
    existing = _config().model_copy(
        update={
            "memory_mode": "shared",
            "memory_data_path": "/private/memory",
            "integrations": (IntegrationConfig(id="codex", enabled=True),),
        }
    )
    answers = iter(
        (
            "3",  # custom provider
            "https://new-provider.example/v1",
            "new-generation",
            "",  # API embeddings
            "",  # same endpoint
            "",  # reuse generation token
            "new-embedding",
            "",  # keep Core ranking; reranker is opt-in
            "",  # apply
        )
    )

    updated = wizard.build_interactive_config(
        input_fn=lambda _prompt: next(answers),
        secret_fn=lambda _prompt: "new-secret",
        output=io.StringIO(),
        existing_config=existing,
        embedding_dimension_loader=lambda _config, _token: 1536,
    )

    assert updated.generation.model == "new-generation"
    assert updated.embedding.api is not None
    assert updated.embedding.api.model == "new-embedding"
    assert updated.semantic_language == existing.semantic_language
    assert updated.memory_mode == "shared"
    assert updated.memory_data_path == "/private/memory"
    assert updated.integrations == existing.integrations
    assert updated.runtime == existing.runtime


def test_default_uninstall_preserves_and_backs_up_memory(tmp_path: Path) -> None:
    paths = InstallerPaths(home_override=tmp_path / "install-home")
    paths.ensure()
    marker = paths.memory_data_dir / "knowledge.db"
    marker.write_bytes(b"opaque-memory")

    result = uninstall(paths=paths)

    assert result["preserved_data"] is True
    assert result["preserved_config"] is True
    assert result["backup_status"] == "created"
    assert marker.read_bytes() == b"opaque-memory"
    archive = Path(result["memory_backup"])
    assert archive.is_file()
    assert archive.stat().st_mode & 0o777 == 0o600
    with tarfile.open(archive, "r:gz") as handle:
        member = handle.extractfile("memory-data/knowledge.db")
        assert member is not None
        assert member.read() == b"opaque-memory"


class _FakeHermesAdapter(BaseTargetAdapter):
    id = "hermes"
    label = "Hermes"

    def __init__(self, root: Path) -> None:
        self.root = root

    def discover(self) -> TargetDiscovery:
        return TargetDiscovery("hermes", "Hermes", True, home=self.root)

    def install(self, context: Any) -> dict[str, Any]:
        del context
        plugin = self.root / "plugins" / "ledgermind-hermes"
        plugin.mkdir(parents=True, exist_ok=True)
        encoded = b'{"enabled": true}\n'
        (plugin / "config.json").write_bytes(encoded)
        (plugin / "installation-record.json").write_text(
            json.dumps(
                {
                    "target": "hermes",
                    "files": {
                        "config.json": {
                            "after": {
                                "content": base64.b64encode(encoded).decode("ascii")
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return {"status": "passed"}

    def verify(self, context: Any) -> dict[str, Any]:
        del context
        return {"status": "passed"}

    def uninstall(self, context: Any, *, purge: bool = False) -> dict[str, Any]:
        del context, purge
        return {"status": "passed"}

    def runtime_environment(self, context: Any) -> dict[str, str]:
        del context
        return {
            "LEDGERMIND_HERMES_CONFIG": str(
                self.root / "plugins" / "ledgermind-hermes" / "config.json"
            )
        }


class _FailingHermesAdapter(_FakeHermesAdapter):
    rolled_back = False

    def verify(self, context: Any) -> dict[str, Any]:
        del context
        raise RuntimeError("verification failed")

    def uninstall(self, context: Any, *, purge: bool = False) -> dict[str, Any]:
        del context, purge
        self.rolled_back = True
        return {"status": "passed"}


def test_integration_lifecycle_is_independent_from_platform_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path / "install")
    write_installer_config(_config(), paths)
    config_writer = importlib.import_module("ledgermind_local.installer.config_writer")

    def unexpected_profile_rewrite(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError(
            "integration lifecycle must not rewrite inference profiles"
        )

    monkeypatch.setattr(
        config_writer, "write_local_profiles", unexpected_profile_rewrite
    )
    adapter = _FakeHermesAdapter(tmp_path / "hermes")
    monkeypatch.setitem(registry._ADAPTERS, "hermes", adapter)

    connected = connect_integration(paths=paths, target_id="hermes")
    set_integration_enabled(paths=paths, target_id="hermes", enabled=False)
    disabled = load_installer_config(paths.config_file)
    disconnected = disconnect_integration(paths=paths, target_id="hermes")
    final = load_installer_config(paths.config_file)

    assert connected["connected"] is True
    assert connected["summary"] == {
        "label": "Hermes",
        "agent_location": str(tmp_path / "hermes"),
        "connected": True,
        "enabled": True,
        "verification": "passed",
        "activation_required": None,
        "memory_mode": "per_agent",
        "memory_space_id": "hermes-default",
        "inference_profiles_preserved": True,
    }
    assert disabled.integrations[0].enabled is False
    assert disconnected["connected"] is False
    assert final.integrations == ()


def test_failed_integration_is_rolled_back_and_not_marked_connected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    paths = InstallerPaths(home_override=tmp_path / "install")
    write_installer_config(_config(), paths)
    adapter = _FailingHermesAdapter(tmp_path / "hermes")
    monkeypatch.setitem(registry._ADAPTERS, "hermes", adapter)

    with pytest.raises(RuntimeError, match="verification failed"):
        connect_integration(paths=paths, target_id="hermes")

    assert adapter.rolled_back is True
    assert load_installer_config(paths.config_file).integrations == ()
