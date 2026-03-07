#!/bin/bash
# Exit on error
set -e

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)/src:$PYTHONPATH

echo "========================================"
echo "🚀 Running Ledgermind Test Suite"
echo "========================================"

# 1. Run all pytest-based tests
# Passing all script arguments to pytest (e.g. -k test_name, -v, etc.)
echo -e "\n[1/3] Running pytest..."
pytest -n0 tests/ "$@"
pytest tests/core/performance/bench_ops.py -n0

# 2. Run Bandit security scan (Local SAST)
echo -e "\n[2/3] Running Bandit Security Scan..."
if command -v bandit &> /dev/null; then
    bandit -r src/ledgermind -ll
else
    echo "⚠️  Warning: bandit is not installed. Skipping security scan."
    echo "Install it using: pip install bandit"
fi

# 3. Run the specialized lg.py script
echo -e "\n[3/3] Running specialized lg.py script..."
python3 tests/lg.py

echo -e "\n✅ All tests completed successfully!"
