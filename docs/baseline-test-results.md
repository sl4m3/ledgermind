# Baseline test results

## Repository

- Repository: `ledgermind-core` (working-tree directory: `ledgermind`)
- Branch: `refactor/rust-core`
- Baseline commit: `63e17e3`
- Baseline tag: `pre-rust-core-boundary`
- Python: `3.11.15`

## Commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTHONPATH="$PWD/src" \
/tmp/ledgermind-venv/bin/python -m pytest -q --tb=short

/tmp/ledgermind-venv/bin/python -m build
```

## Results

- Pytest: **150 passed**.
- Build: **passed**; sdist and wheel produced for `ledgermind-core==4.0.0a1`.

## Known skipped checks

- Rust checks are not applicable at baseline: the repository is still the Python Core and has no Cargo workspace.
- `cargo deny` is not applicable until the Rust workspace is created in Stage 8.
- Ruff and mypy were not part of the Stage 0 baseline command set; they remain required for subsequent Python changes.
