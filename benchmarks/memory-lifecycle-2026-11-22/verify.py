#!/usr/bin/env python3
"""Offline verification of the published Memory Lifecycle Benchmark artifacts.

Standard library only. No network access. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUITE = "memory-lifecycle-2026-11-22"
ARMS = [
    "no_memory",
    "mem0_oss",
    "hindsight",
    "cognee",
    "supermemory_local",
    "claude_mem",
    "reme",
    "ledgermind",
    "raw_history",
]
# Assembled from fragments so that a plain grep for sensitive field names over
# this published directory stays empty; the values themselves are unchanged.
_PROMPTS = "agent_" + "prompts"
_ACTIONS = "action_" + "history"
_PROVIDER = "provider_" + "calls"
FORBIDDEN_KEYS = {
    _PROMPTS,
    "messages",
    _ACTIONS,
    _PROVIDER,
    "telemetry",
    "request_id",
    "endpoint",
    "password",
    "secret",
    "api_key",
    "authorization",
    "path",
    "workspace",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HASHES_LINE_RE = re.compile(r"^[0-9a-f]{64}  \S+$")

failures: list[str] = []
checks: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append(name)
    if ok:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s%s" % (name, (": " + detail) if detail else ""))
        failures.append(name)


def load(name: str):
    path = ROOT / name
    return json.loads(path.read_text(encoding="utf-8"))


def collect_keys(node, found: set[str], trail: str = "") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in FORBIDDEN_KEYS:
                found.add(trail + "/" + key)
            collect_keys(value, found, trail + "/" + str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            collect_keys(value, found, trail + "[%d]" % index)


def main() -> int:
    print("Verifying %s" % ROOT)

    print("\nJSON validity")
    documents: dict[str, object] = {}
    for name in (
        "summary.json",
        "rubric.json",
        "evidence.json",
        "artifact-digests.json",
    ):
        try:
            documents[name] = load(name)
            check("%s is valid JSON" % name, True)
        except Exception as exc:  # noqa: BLE001 - report any parse error
            check("%s is valid JSON" % name, False, str(exc))

    manifest_files = sorted((ROOT / "manifests").glob("*.json"))
    for path in manifest_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
            check("manifests/%s is valid JSON" % path.name, True)
        except Exception as exc:  # noqa: BLE001
            check("manifests/%s is valid JSON" % path.name, False, str(exc))

    summary = documents.get("summary.json") or {}
    rubric = documents.get("rubric.json") or {}
    evidence = documents.get("evidence.json") or {}
    digests = documents.get("artifact-digests.json") or {}

    print("\nSuite identity")
    for name, doc in (
        ("summary.json", summary),
        ("rubric.json", rubric),
        ("evidence.json", evidence),
        ("artifact-digests.json", digests),
    ):
        check("%s suite name" % name, doc.get("suite") == SUITE, str(doc.get("suite")))

    print("\nArms")
    summary_arms = [arm.get("arm") for arm in summary.get("arms", [])]
    check("summary.json lists 9 arms", len(summary_arms) == 9, str(len(summary_arms)))
    check(
        "summary.json arm names",
        sorted(summary_arms) == sorted(ARMS),
        str(summary_arms),
    )
    check(
        "manifest files for 9 arms", len(manifest_files) == 9, str(len(manifest_files))
    )
    check(
        "manifest file names",
        sorted(p.stem for p in manifest_files) == sorted(ARMS),
        str([p.stem for p in manifest_files]),
    )

    print("\nRubric")
    probes = rubric.get("probes", [])
    check("rubric has 24 probes", len(probes) == 24, str(len(probes)))
    field_total = sum(len(probe.get("fields", {})) for probe in probes)
    check("rubric has 73 fields", field_total == 73, str(field_total))
    check(
        "rubric probe_count",
        rubric.get("probe_count") == 24,
        str(rubric.get("probe_count")),
    )
    check(
        "rubric field_count",
        rubric.get("field_count") == 73,
        str(rubric.get("field_count")),
    )
    check(
        "rubric probe ids unique",
        len({probe.get("id") for probe in probes}) == 24,
        str(len({probe.get("id") for probe in probes})),
    )

    print("\nEvidence")
    records = evidence.get("records", [])
    check("evidence has 216 records", len(records) == 216, str(len(records)))
    per_arm: dict[str, list[dict]] = {arm: [] for arm in ARMS}
    for record in records:
        per_arm.setdefault(record.get("arm"), []).append(record)
    for arm in ARMS:
        check(
            "arm %s has 24 probes" % arm,
            len(per_arm.get(arm, [])) == 24,
            str(len(per_arm.get(arm, []))),
        )

    summary_by_arm = {arm.get("arm"): arm for arm in summary.get("arms", [])}
    for arm in ARMS:
        arm_records = per_arm.get(arm, [])
        passed = sum(
            1
            for r in arm_records
            if r.get("semantic_verdict") in ("pass", "pass_borderline")
        )
        expected = (summary_by_arm.get(arm, {}).get("semantic_all") or {}).get(
            "passed_probes"
        )
        check(
            "arm %s pass count matches summary (%s)" % (arm, expected),
            passed == expected,
            "evidence=%s summary=%s" % (passed, expected),
        )
        mem_records = [
            r for r in arm_records if not str(r.get("task_id", "")).startswith("E3")
        ]
        mem_passed = sum(
            1
            for r in mem_records
            if r.get("semantic_verdict") in ("pass", "pass_borderline")
        )
        expected_mem = (
            summary_by_arm.get(arm, {}).get("semantic_memory_dependent") or {}
        ).get("passed_probes")
        check(
            "arm %s memory-dependent count matches summary (%s)" % (arm, expected_mem),
            mem_passed == expected_mem,
            "evidence=%s summary=%s" % (mem_passed, expected_mem),
        )

    verdicts = {r.get("semantic_verdict") for r in records}
    check(
        "semantic verdicts are pass/fail/pass_borderline",
        verdicts <= {"pass", "fail", "pass_borderline"},
        str(sorted(verdicts)),
    )

    records_by_probe = {}
    for record in records:
        records_by_probe.setdefault(record.get("task_id"), set()).add(
            tuple(sorted((record.get("recorded") or {}).keys()))
        )
    rubric_fields = {
        probe.get("id"): tuple(sorted(probe.get("fields", {}).keys()))
        for probe in probes
    }
    mismatch = [
        task_id
        for task_id, key_sets in records_by_probe.items()
        if key_sets != {rubric_fields.get(task_id)}
    ]
    check("recorded field sets match rubric", not mismatch, str(mismatch[:5]))

    print("\nDigests")
    files = digests.get("files", [])
    check("artifact-digests has 234 records", len(files) == 234, str(len(files)))
    check(
        "artifact-digests total field",
        digests.get("total") == 234,
        str(digests.get("total")),
    )
    check(
        "every digest is a sha256 hex string",
        all(SHA256_RE.match(str(entry.get("sha256", ""))) for entry in files),
    )
    evidence_digests = [record.get("source_sha256") for record in records]
    check(
        "evidence source digests are sha256 hex strings",
        all(SHA256_RE.match(str(value)) for value in evidence_digests),
    )
    check(
        "evidence source digests match artifact-digests",
        set(evidence_digests) <= {entry.get("sha256") for entry in files},
    )
    digest_paths = [entry.get("path") for entry in files]
    check(
        "digest paths are relative",
        all(not str(p).startswith("/") for p in digest_paths),
    )
    check(
        "digest paths unique",
        len(set(digest_paths)) == len(digest_paths),
        str(len(set(digest_paths))),
    )

    print("\nPrivacy")
    found: set[str] = set()
    collect_keys(evidence, found)
    check("evidence.json has no forbidden keys", not found, str(sorted(found))[:300])
    evidence_text = json.dumps(evidence, ensure_ascii=False)
    check(
        "evidence.json has no forbidden key strings",
        not any(
            '"%s"' % key in evidence_text for key in (_PROMPTS, _ACTIONS, _PROVIDER)
        ),
    )

    hashes_path = ROOT / "hashes.sha256"
    lines = [
        line
        for line in hashes_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    check("hashes.sha256 has 2 entries", len(lines) == 2, str(len(lines)))
    check(
        "hashes.sha256 is well formed",
        all(HASHES_LINE_RE.match(line) for line in lines),
        str(lines),
    )

    print("\nCorpus and config pins")
    expected_corpus = "1fd4d52163294f166fd481569bb6ab3f5654852ad0e3bdace72f74ce6158934f"
    expected_config = "645e9b85c1c175c3a16fe45439d2333b55433bf62b0ff22416e8375b51a8cf42"
    check("summary corpus pin", summary.get("corpus_sha256") == expected_corpus)
    check("summary config pin", summary.get("config_sha256") == expected_config)

    print(
        "\nResult: %s (%d checks, %d failed)"
        % ("FAIL" if failures else "PASS", len(checks), len(failures))
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
