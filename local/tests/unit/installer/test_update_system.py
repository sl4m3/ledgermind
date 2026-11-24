from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import zstandard
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ledgermind_local.installer import cli
from ledgermind_local.installer.download import download_artifact
from ledgermind_local.installer.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
)
from ledgermind_local.installer.operations.common import (
    DEFAULT_RELEASE_BASE_URL,
    DEFAULT_RELEASE_TAG_BASE_URL,
    assemble_layered_bundle,
    compute_runtime_layer_digest,
    prune_old_releases,
    resolve_release_base_url,
    write_update_check_cache,
)
from ledgermind_local.installer.operations.update import check_update, rollback, update
from ledgermind_local.installer.paths import InstallerPaths
from ledgermind_local.installer.preflight import platform_id
from ledgermind_local.installer.verify import sha256_file, verify_bundle_tree


def _config() -> InstallerConfig:
    return InstallerConfig(
        semantic_language="en",
        generation=GenerationConfig(
            endpoint="https://provider.example/v1",
            token="gen-secret",
            model="gen-model",
        ),
        embedding=EmbeddingConfig(
            mode="api",
            api=EmbeddingApiConfig(
                endpoint="https://provider.example/v1",
                token="emb-secret",
                model="emb-model",
                dimensions=3,
            ),
        ),
    )


def _create_signed_bundle(
    root: Path,
    *,
    release_version: str,
    manifest_key: Ed25519PrivateKey,
    core_key: Ed25519PrivateKey,
    marker_text: str,
    runtime_payload: bytes = b"python-runtime-bytes",
    weights_payload: bytes = b"embedding-runtime-weights",
) -> Path:
    bundle = root / "bundle"
    for rel in (
        "bin",
        "signatures",
        "python/local/ledgermind_local",
        "python/runtime/bin",
        "embedding-runtimes/model-a",
    ):
        (bundle / rel).mkdir(parents=True, exist_ok=True)
    core_bytes = f"#!/bin/sh\necho core-{release_version}\n".encode()
    (bundle / "bin" / "ledgermind-core").write_bytes(core_bytes)
    os.chmod(bundle / "bin" / "ledgermind-core", 0o700)
    (bundle / "bin" / "ledgermind").write_text(
        f"#!/bin/sh\necho cli-{release_version}\n", encoding="utf-8"
    )
    os.chmod(bundle / "bin" / "ledgermind", 0o700)
    (bundle / "python" / "local" / "ledgermind_local" / "marker.txt").write_text(
        marker_text, encoding="utf-8"
    )
    (bundle / "python" / "runtime" / "bin" / "python3.12").write_bytes(runtime_payload)
    os.chmod(bundle / "python" / "runtime" / "bin" / "python3.12", 0o755)
    link = bundle / "python" / "runtime" / "bin" / "python3"
    if not link.exists():
        link.symlink_to("python3.12")
    (bundle / "embedding-runtimes" / "model-a" / "weights.bin").write_bytes(
        weights_payload
    )

    pub_raw = manifest_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    core_pub = core_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    (bundle / "signatures" / "manifest.pub").write_bytes(pub_raw)
    (bundle / "signatures" / "ledgermind-core.pub").write_bytes(core_pub)
    (bundle / "signatures" / "ledgermind-core.sig").write_bytes(core_key.sign(core_bytes))

    artifacts: dict[str, dict[str, object]] = {}
    for item in sorted(bundle.rglob("*")):
        if item.is_file() and not item.is_symlink():
            rel = str(item.relative_to(bundle))
            if rel in {"bundle-manifest.json", "signatures/manifest.sig"}:
                continue
            artifacts[rel] = {
                "size": item.stat().st_size,
                "sha256": sha256_file(item),
            }
    manifest_payload = {
        "schema_version": 1,
        "release_version": release_version,
        "platform": platform_id(),
        "artifacts": artifacts,
    }
    bm_bytes = (
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (bundle / "bundle-manifest.json").write_bytes(bm_bytes)
    (bundle / "signatures" / "manifest.sig").write_bytes(manifest_key.sign(bm_bytes))
    return bundle


def _pack_zst(bundle_dir: Path, archive_path: Path, *, exclude_runtime: bool) -> None:
    tar_path = archive_path.with_suffix("")
    with tarfile.open(tar_path, "w") as tar:
        for item in sorted(bundle_dir.rglob("*")):
            rel = item.relative_to(bundle_dir)
            rel_posix = rel.as_posix()
            if exclude_runtime and (
                rel_posix in {"embedding-runtimes", "python/runtime"}
                or rel_posix.startswith(("embedding-runtimes/", "python/runtime/"))
            ):
                continue
            tar.add(item, arcname=f"bundle/{rel_posix}", recursive=False)
    compressed = zstandard.ZstdCompressor().compress(tar_path.read_bytes())
    archive_path.write_bytes(compressed)
    tar_path.unlink(missing_ok=True)


def test_resolve_release_base_url_defaults_tag_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LEDGERMIND_RELEASE_BASE_URL", raising=False)
    assert resolve_release_base_url() == f"{DEFAULT_RELEASE_BASE_URL}/"
    tag_prefix = f"{DEFAULT_RELEASE_TAG_BASE_URL}/v"
    assert resolve_release_base_url(version="1.0.1") == f"{tag_prefix}1.0.1/"
    assert resolve_release_base_url(version="v" + "1.0.2") == f"{tag_prefix}1.0.2/"
    monkeypatch.setenv("LEDGERMIND_RELEASE_BASE_URL", "https://mirror.example/rel")
    assert resolve_release_base_url(version="1.0.1") == "https://mirror.example/rel/"


def test_download_artifact_uses_verified_cache_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "downloads" / "artifact.tar.zst"
    dest.parent.mkdir(parents=True)
    payload = b"cached-signed-archive"
    dest.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    seen_progress: list[tuple[int, int | None]] = []

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("network must not be touched on cache hit")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    result = download_artifact(
        "https://mirror.example/artifact.tar.zst",
        dest,
        expected_size=len(payload),
        expected_sha256=digest,
        progress=lambda done, total: seen_progress.append((done, total)),
    )

    assert result.path == dest
    assert result.size == len(payload)
    assert result.sha256 == digest
    assert seen_progress == [(len(payload), len(payload))]


def test_layered_patch_assembly_hardlinks_runtime_and_verifies_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LEDGERMIND_RELEASE_BASE_URL", raising=False)
    paths = InstallerPaths(home_override=tmp_path / "home")
    paths.ensure()
    manifest_key = Ed25519PrivateKey.generate()
    core_key = Ed25519PrivateKey.generate()
    pub_raw = manifest_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    old_bundle = _create_signed_bundle(
        tmp_path / "build-old",
        release_version="1.0.0",
        manifest_key=manifest_key,
        core_key=core_key,
        marker_text="old-marker",
    )
    old_installed = paths.release_dir("1.0.0")
    old_installed.parent.mkdir(parents=True, exist_ok=True)
    old_bundle.rename(old_installed)
    paths.current_link.symlink_to(old_installed)

    runtime_digest = compute_runtime_layer_digest(old_installed / "bundle-manifest.json")
    assert runtime_digest is not None

    new_bundle = _create_signed_bundle(
        tmp_path / "build-new",
        release_version="1.0.1",
        manifest_key=manifest_key,
        core_key=core_key,
        marker_text="new-marker",
    )
    assert compute_runtime_layer_digest(new_bundle / "bundle-manifest.json") == runtime_digest

    repo_dir = tmp_path / "release-repo"
    repo_dir.mkdir()
    plat = platform_id()
    full_archive = repo_dir / f"ledgermind-{plat}.tar.zst"
    patch_archive = repo_dir / f"ledgermind-patch-{plat}.tar.zst"
    _pack_zst(new_bundle, full_archive, exclude_runtime=False)
    _pack_zst(new_bundle, patch_archive, exclude_runtime=True)
    assert patch_archive.stat().st_size < full_archive.stat().st_size

    install_manifest_payload = {
        "schema_version": 1,
        "release_version": "1.0.1",
        "published_at": "2026-11-24T12:00:00Z",
        "public_key_fingerprint": hashlib.sha256(pub_raw).hexdigest(),
        "platforms": {
            plat: {
                "installer": {
                    "url": "ledgermind-installer",
                    "size": 1,
                    "sha256": "0" * 64,
                    "platform": plat,
                },
                "bundle": {
                    "url": full_archive.name,
                    "size": full_archive.stat().st_size,
                    "sha256": sha256_file(full_archive),
                    "signature": base64.b64encode(
                        manifest_key.sign(full_archive.read_bytes())
                    ).decode("ascii"),
                    "platform": plat,
                },
            }
        },
        "components": {
            "layered_update": {
                plat: {
                    "base_runtime_sha256": runtime_digest,
                    "patch": {
                        "url": patch_archive.name,
                        "size": patch_archive.stat().st_size,
                        "sha256": sha256_file(patch_archive),
                        "signature": base64.b64encode(
                            manifest_key.sign(patch_archive.read_bytes())
                        ).decode("ascii"),
                        "platform": plat,
                    },
                }
            }
        },
    }
    manifest_file = repo_dir / "install-manifest.json"
    sig_file = repo_dir / "install-manifest.sig"
    manifest_bytes = json.dumps(install_manifest_payload, indent=2).encode("utf-8")
    manifest_file.write_bytes(manifest_bytes)
    sig_file.write_bytes(manifest_key.sign(manifest_bytes))

    monkeypatch.setenv("LEDGERMIND_RELEASE_BASE_URL", repo_dir.as_uri())

    summary = check_update(paths=paths, public_key=pub_raw)
    assert summary["installed_version"] == "1.0.0"
    assert summary["latest_version"] == "1.0.1"
    assert summary["update_available"] is True
    assert summary["layered_patch_available"] is True
    assert summary["download_bytes"] == patch_archive.stat().st_size

    from ledgermind_local.installer.manifest import load_manifest

    loaded_manifest = load_manifest(manifest_file)
    assembled = assemble_layered_bundle(
        paths=paths,
        manifest=loaded_manifest,
        current_release=old_installed,
        public_key=pub_raw,
    )
    assert assembled is not None
    verified = verify_bundle_tree(assembled, public_key=pub_raw)
    assert verified["status"] == "passed"
    assert (
        assembled / "python" / "local" / "ledgermind_local" / "marker.txt"
    ).read_text(encoding="utf-8") == "new-marker"
    # Verify immutable runtime file was hardlinked when on same filesystem
    assert (
        os.stat(assembled / "embedding-runtimes" / "model-a" / "weights.bin").st_ino
        == os.stat(
            old_installed / "embedding-runtimes" / "model-a" / "weights.bin"
        ).st_ino
    )

    # Mismatched runtime digest must cleanly return None so caller falls back to full bundle
    bad_payload = json.loads(manifest_bytes.decode("utf-8"))
    bad_payload["components"]["layered_update"][plat]["base_runtime_sha256"] = "f" * 64
    bad_manifest = tmp_path / "bad-manifest.json"
    bad_manifest.write_text(json.dumps(bad_payload), encoding="utf-8")
    assert (
        assemble_layered_bundle(
            paths=paths,
            manifest=load_manifest(bad_manifest),
            current_release=old_installed,
            public_key=pub_raw,
        )
        is None
    )


def test_update_up_to_date_short_circuit_prune_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = InstallerPaths(home_override=tmp_path / "home")
    paths.ensure()
    monkeypatch.setenv("LEDGERMIND_SECRET_BACKEND", "file")
    from ledgermind_local.installer.config_writer import write_installer_config

    write_installer_config(_config(), paths)
    manifest_key = Ed25519PrivateKey.generate()
    core_key = Ed25519PrivateKey.generate()
    pub_raw = manifest_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    for idx, ver in enumerate(("1.0.0", "1.0.1", "1.0.2")):
        built = _create_signed_bundle(
            tmp_path / f"b-{ver}",
            release_version=ver,
            manifest_key=manifest_key,
            core_key=core_key,
            marker_text=ver,
        )
        dest = paths.release_dir(ver)
        built.rename(dest)
        os.utime(dest, (1_700_000_000 + idx * 10, 1_700_000_000 + idx * 10))

    paths.current_link.symlink_to(paths.release_dir("1.0.2"))

    # Prune keeping 2 newest (1.0.2 + 1.0.1) removes 1.0.0
    pruned = prune_old_releases(paths, keep=2)
    assert pruned == ["1.0.0"]
    assert not paths.release_dir("1.0.0").exists()
    assert paths.release_dir("1.0.1").is_dir()
    assert paths.release_dir("1.0.2").is_dir()

    # Up-to-date online update returns immediately without calling install()
    update_mod = importlib.import_module(
        "ledgermind_local.installer.operations.update"
    )
    fake_manifest = SimpleNamespace(
        release_version="1.0.2",
        published_at="2026-11-24T12:00:00Z",
        components={},
    )
    monkeypatch.setattr(
        update_mod,
        "fetch_manifest",
        lambda *_a, **_k: (
            tmp_path / "m.json",
            tmp_path / "m.sig",
            fake_manifest,
        ),
    )
    monkeypatch.setattr(
        update_mod,
        "install",
        lambda **_k: pytest.fail("install must not run when already up to date"),
    )
    res = update(config=_config(), paths=paths, public_key=pub_raw)
    assert res["up_to_date"] is True
    assert res["delivery_mode"] == "up-to-date"

    # Rollback from 1.0.2 to 1.0.1 verifies bundle and updates current + bin symlink
    monkeypatch.setattr(
        update_mod,
        "verify_bundle_tree",
        lambda *_a, **_k: {"status": "passed"},
    )
    monkeypatch.setattr(
        update_mod,
        "doctor",
        lambda **_k: {"status": "passed"},
    )
    rb = rollback(paths=paths)
    assert rb["previous_version"] == "1.0.2"
    assert rb["release_version"] == "1.0.1"
    assert paths.current_link.resolve() == paths.release_dir("1.0.1").resolve()

    # Rollback failure preserves active release link (now 1.0.1)
    monkeypatch.setattr(
        update_mod,
        "doctor",
        lambda **_k: {"status": "failed"},
    )
    with pytest.raises(RuntimeError, match="rollback failed"):
        rollback(paths=paths, target_version="1.0.2")
    assert paths.current_link.resolve() == paths.release_dir("1.0.1").resolve()


def test_cli_update_check_rollback_and_status_notice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = InstallerPaths(home_override=tmp_path / "cli-home")
    paths.ensure()

    for argv, snippet in (
        (["update", "--help"], "layered patches"),
        (["rollback", "--help"], "Restore"),
    ):
        with pytest.raises(SystemExit) as exc:
            cli.main(argv)
        assert exc.value.code == 0
        assert snippet.lower() in capsys.readouterr().out.lower()

    monkeypatch.setattr(
        cli,
        "check_update",
        lambda **_k: {
            "status": "passed",
            "installed_version": "5.0.2",
            "latest_version": "5.0.3",
            "release_version": "5.0.3",
            "update_available": True,
            "layered_patch_available": True,
            "download_bytes": 24 * 1024 * 1024,
            "full_bundle_bytes": 670 * 1024 * 1024,
        },
    )
    assert cli.main(["update", "--check", "--home", str(paths.home_override)]) == 0
    check_out = capsys.readouterr().out
    assert "Update check:" in check_out
    assert "Latest:       5.0.3" in check_out
    assert "layered patch (~24.0 MiB vs 670.0 MiB full)" in check_out

    monkeypatch.setattr(
        cli,
        "rollback",
        lambda **_k: {
            "status": "passed",
            "previous_version": "5.0.3",
            "release_version": "5.0.2",
            "release_dir": str(paths.release_dir("5.0.2")),
            "doctor": {"status": "passed"},
        },
    )
    assert cli.main(["rollback", "--home", str(paths.home_override)]) == 0
    rb_out = capsys.readouterr().out
    assert "Rollback:" in rb_out
    assert "Version:      5.0.3 -> 5.0.2" in rb_out

    write_update_check_cache(
        paths,
        {
            "installed_version": "5.0.2",
            "latest_version": "5.0.3",
            "update_available": True,
        },
    )
    status_res = cli._result(
        "status",
        payload={
            "installed": True,
            "current": str(paths.release_dir("5.0.2")),
            "config": str(paths.config_file),
            "config_exists": True,
            "memory_health": {"status": "healthy"},
            "update_check": {
                "installed_version": "5.0.2",
                "latest_version": "5.0.3",
                "update_available": True,
            },
        },
    )
    cli._emit(status_res, json_output=False)
    status_out = capsys.readouterr().out
    assert "Available:    5.0.2 -> 5.0.3 (run 'ledgermind update')" in status_out
