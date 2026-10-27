#!/bin/sh
# Run the public LedgerMind test suites: protocol contracts, agent adapters and
# the Busl Local product. Everything here must run without proprietary code.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UV=${UV:-uv}
PYTHON=${LEDGERMIND_TEST_PYTHON:-3.13}
FAILED=""

section() {
    printf '\n=== %s ===\n' "$1"
}

note() {
    printf '%s: %s\n' "$1" "$2"
}

run_python() {
    name=$1
    dir=$2
    shift 2
    section "$name"
    if (cd "$ROOT/$dir" && $UV run --python "$PYTHON" --no-project "$@" python -m pytest -q); then
        note "$name" ok
    else
        note "$name" FAILED
        FAILED="$FAILED $name"
    fi
}

# The Local product depends on the proprietary ledgermind-inference wheel,
# published as a release asset (see local/release/dependency-wheels.json). CI
# downloads it; development may point at a locally built wheel or, when the
# private platform is checked out beside this repository, at its sources.
if [ -n "${LEDGERMIND_INFERENCE_WHEEL:-}" ]; then
    INFERENCE_DEP="--with $LEDGERMIND_INFERENCE_WHEEL"
elif [ -d "$ROOT/../inference/src" ]; then
    INFERENCE_DEP="--with-editable $ROOT/../inference"
else
    printf '%s\n' \
        'ledgermind-inference is required for the Local suite.' \
        'Set LEDGERMIND_INFERENCE_WHEEL to the release wheel, or check out the' \
        'private platform repository beside this one.' >&2
    exit 1
fi

run_python protocol protocol/python \
    --with-editable . --with pytest --with jsonschema

run_python integrations integrations \
    --with-editable . --with-editable ../protocol/python --with pytest

run_python local local \
    $INFERENCE_DEP \
    --with-editable ../protocol/python \
    --with-editable '.[dev]' \
    --with pytest --with pip --with setuptools --with wheel

section summary
if [ -n "$FAILED" ]; then
    printf 'failed:%s\n' "$FAILED"
    exit 1
fi
printf 'all suites ok\n'
