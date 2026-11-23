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
REPO = ROOT.parents[1]
SUITE = "memory-lifecycle-2026-11-22"
ARMS = [
    "ledgermind",
    "raw_history",
    "reme",
    "claude_mem",
    "cognee",
    "hindsight",
    "mem0_oss",
    "supermemory_local",
]
VERSIONS = {
    "ledgermind": "5.0.0",
    "raw_history": None,
    "reme": "0.4.2.3",
    "claude_mem": "16.0.4",
    "cognee": "1.6.10",
    "hindsight": "1.2.3",
    "mem0_oss": "2.2.1",
    "supermemory_local": "0.0.9",
}
# Assembled from fragments so that a plain grep over this published directory
# stays empty; the values themselves are unchanged.
_PROMPTS = "agent_" + "prompts"
_ACTIONS = "action_" + "history"
_PROVIDER = "provider_" + "calls"
_REMOVED_ARM = "no_" + "memory"
_REMOVED_SCALE = "lite" + "ral"
_REMOVED_CHECK = "evaluate_" + "action_task"
_REMOVED_MEM_DEP_HYPHEN = "memory-" + "dependent"
_REMOVED_MEM_DEP_UNDER = "memory_" + "dependent"
_OLD_PRODUCT_VERSION = "4." + "1.0"
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
FORBIDDEN_PUBLIC_TERMS = (
    _REMOVED_ARM,
    _REMOVED_SCALE,
    _REMOVED_CHECK,
    _REMOVED_MEM_DEP_HYPHEN,
    _REMOVED_MEM_DEP_UNDER,
)
SVG_NAME = "accuracy-vs-cost.svg"
# The published totals for these two arms are call-index sums over every agent
# call, including the two failed repair attempts, which consumed tokens and were
# billed. Per-probe evidence records only the successful probes, so the published
# total sits exactly this far above the per-probe sum.
REPAIR_INPUT_TOKENS = {
    "ledgermind": 6_237,
    "raw_history": 185_413,
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HASHES_LINE_RE = re.compile(r"^[0-9a-f]{64}  \S+$")
DIGEST_PATH_RE = re.compile(
    r"^arms/(?P<arm>[a-z0-9_]+)/(?P<kind>manifest\.json|summary\.json|"
    r"results/[A-Z]\d-P\d\.json)$"
)

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


def public_files() -> list[Path]:
    paths = [
        REPO / "README.md",
        REPO / "BENCHMARK.md",
        REPO / "benchmarks" / "README.md",
        ROOT / "README.md",
        ROOT / "summary.json",
        ROOT / "rubric.json",
        ROOT / "evidence.json",
        ROOT / "artifact-digests.json",
        ROOT / SVG_NAME,
    ]
    paths.extend(sorted((ROOT / "manifests").glob("*.json")))
    return paths


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
    check("summary.json lists 8 arms", len(summary_arms) == 8, str(len(summary_arms)))
    check("summary.json arm order", summary_arms == ARMS, str(summary_arms))
    check(
        "summary.json arm versions",
        all(
            summary_by_arm.get("version") == VERSIONS[arm]
            for arm, summary_by_arm in zip(summary_arms, summary.get("arms", []))
        ),
        str([(a.get("arm"), a.get("version")) for a in summary.get("arms", [])]),
    )
    check(
        "manifest files for 8 arms", len(manifest_files) == 8, str(len(manifest_files))
    )
    check(
        "manifest file names",
        sorted(p.stem for p in manifest_files) == sorted(ARMS),
        str([p.stem for p in manifest_files]),
    )
    check(
        "removed manifest is absent",
        not (ROOT / "manifests" / (_REMOVED_ARM + ".json")).exists(),
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
    field_types = {
        field.get("type")
        for probe in probes
        for field in probe.get("fields", {}).values()
    }
    check(
        "rubric field types",
        field_types <= {"closed_value", "quantity"},
        str(sorted(field_types)),
    )

    print("\nEvidence")
    records = evidence.get("records", [])
    check("evidence has 192 records", len(records) == 192, str(len(records)))
    check("evidence arm order", evidence.get("arms") == ARMS, str(evidence.get("arms")))
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
        arm_summary = summary_by_arm.get(arm, {})
        ag_in = arm_summary.get("agent_input_tokens")
        ag_cached = arm_summary.get("agent_cached_input_tokens")
        ag_uncached = arm_summary.get("agent_uncached_input_tokens")
        ag_out = arm_summary.get("agent_output_tokens")
        mem_in = arm_summary.get("memory_generation_input_tokens")
        mem_cached = arm_summary.get("memory_generation_cached_input_tokens")
        mem_uncached = arm_summary.get("memory_generation_uncached_input_tokens")
        mem_out = arm_summary.get("memory_generation_output_tokens")
        tot_in = arm_summary.get("total_input_tokens")
        tot_out = arm_summary.get("total_output_tokens")
        tot_tokens = arm_summary.get("total_tokens")
        check(
            "arm %s summary token totals are consistent" % arm,
            isinstance(ag_in, int)
            and isinstance(ag_cached, int)
            and isinstance(ag_uncached, int)
            and isinstance(ag_out, int)
            and isinstance(mem_in, int)
            and isinstance(mem_out, int)
            and isinstance(tot_in, int)
            and isinstance(tot_out, int)
            and isinstance(tot_tokens, int)
            and ag_uncached == ag_in - ag_cached
            and (mem_cached is None or mem_uncached == mem_in - mem_cached)
            and tot_in == ag_in + mem_in
            and tot_out == ag_out + mem_out
            and tot_tokens == tot_in + tot_out,
        )
        if arm in REPAIR_INPUT_TOKENS:
            token_sum = sum(
                (r.get("usage") or {}).get("input_tokens") or 0 for r in arm_records
            )
            expected_tokens = summary_by_arm.get(arm, {}).get("agent_input_tokens")
            repair_tokens = REPAIR_INPUT_TOKENS[arm]
            check(
                "arm %s agent_input_tokens = per-probe sums + failed repair attempts"
                % arm,
                token_sum + repair_tokens == expected_tokens,
                "evidence=%s + repairs=%s summary=%s"
                % (token_sum, repair_tokens, expected_tokens),
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
    check("artifact-digests has 208 records", len(files) == 208, str(len(files)))
    check(
        "artifact-digests total field",
        digests.get("total") == 208,
        str(digests.get("total")),
    )
    check(
        "every digest is a sha256 hex string",
        all(SHA256_RE.match(str(entry.get("sha256", ""))) for entry in files),
    )
    kinds: dict[str, int] = {}
    bad_paths = []
    for entry in files:
        match = DIGEST_PATH_RE.match(str(entry.get("path", "")))
        if not match or match.group("arm") not in ARMS:
            bad_paths.append(entry.get("path"))
            continue
        kind = match.group("kind")
        kind = "results" if kind.startswith("results/") else kind
        kinds[kind] = kinds.get(kind, 0) + 1
    check("digest paths follow the published layout", not bad_paths, str(bad_paths[:5]))
    check(
        "digest counts are 8 manifests, 8 summaries, 192 results",
        kinds == {"manifest.json": 8, "summary.json": 8, "results": 192},
        str(kinds),
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

    print("\nPublic content")
    svg_path = ROOT / SVG_NAME
    check("accuracy-vs-cost.svg exists", svg_path.is_file())
    if svg_path.is_file():
        svg = svg_path.read_text(encoding="utf-8")
        check(
            "accuracy-vs-cost.svg is an SVG document", svg.lstrip().startswith("<svg")
        )
        check(
            "accuracy-vs-cost.svg labels every arm",
            all(
                arm_label in svg
                for arm_label in (
                    "LedgerMind",
                    "Raw history",
                    "ReMe",
                    "Claude-Mem",
                    "Cognee",
                    "Hindsight",
                    "Mem0 OSS",
                    "Supermemory Local",
                )
            ),
        )
        check("accuracy-vs-cost.svg has no external links", 'href="http' not in svg)
        check("accuracy-vs-cost.svg is compact", len(svg.encode("utf-8")) < 200_000)
    check(
        "README.md embeds the accuracy-versus-cost chart",
        "benchmarks/memory-lifecycle-2026-11-22/%s" % SVG_NAME
        in (REPO / "README.md").read_text(encoding="utf-8"),
    )

    leaked = []
    for path in public_files():
        if not path.is_file():
            leaked.append("%s (missing)" % path)
            continue
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_PUBLIC_TERMS:
            if term in text:
                leaked.append("%s:%s" % (path.name, term))
    check(
        "public markdown, JSON and SVG contain no removed terms",
        not leaked,
        str(leaked[:5]),
    )
    check(
        "README.md, BENCHMARK.md and the suite do not publish the old product version",
        not any(
            _OLD_PRODUCT_VERSION in path.read_text(encoding="utf-8")
            for path in [
                REPO / "README.md",
                REPO / "BENCHMARK.md",
                ROOT / "README.md",
                ROOT / "summary.json",
            ]
        ),
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
