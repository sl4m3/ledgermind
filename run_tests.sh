#!/bin/bash
# Exit on error
set -e

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✅ Activated virtual environment: .venv"
fi

# Set PYTHONPATH to include the src directory
export PYTHONPATH=$(pwd)/src:$PYTHONPATH

echo "========================================"
echo "🚀 Running Ledgermind Test Suite"
echo "========================================"

# Pre-run Cleanup
rm -rf MagicMock temp_test_tools temp_test_heartbeat memory_lifecycle_test .ledgermind_fallback

# 1. Run all pytest-based tests
echo -e "\n[1/3] Running pytest..."
pytest -n0 --maxfail=5 tests/ "$@"
pytest tests/core/performance/bench_ops.py -n0

# 2. Run Bandit security scan (Local SAST)
echo -e "\n[2/3] Running Bandit Security Scan..."
if command -v bandit &> /dev/null; then
    bandit -r src/ledgermind -ll
else
    echo "⚠️  Warning: bandit is not installed. Skipping security scan."
fi

# 3. Run the specialized lg.py script
echo -e "\n[3/3] Running specialized lg.py script..."
python3 tests/lg.py

# Final Cleanup
rm -rf MagicMock temp_test_tools temp_test_heartbeat memory_lifecycle_test .ledgermind_fallback

echo -e "\n✅ All tests completed successfully!"
