#!/bin/bash
# Run unit tests in a sandboxed environment.
#
# Usage:
#   ./run_tests.sh                              # Run all tests
#   ./run_tests.sh tests/test_specific.py       # Run specific test file
#   ./run_tests.sh -v tests/                    # Verbose, run all tests
#
# This script is designed to be executed inside a container or cube sandbox.
# It expects the code to be available under /workspace or the current directory.

set -euo pipefail

# Configuration
TEST_DIR="${1:-tests}"
PYTHON="${PYTHON:-python3}"
COVERAGE="${COVERAGE:-}"

echo "=== Code Review Agent: Test Runner ==="
echo "Python:    $($PYTHON --version 2>&1)"
echo "Test dir:  $TEST_DIR"
echo "Date:      $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""

# Check if pytest is available
if ! $PYTHON -c "import pytest" 2>/dev/null; then
    echo "⚠️  pytest not found, installing..."
    pip install pytest -q 2>/dev/null || {
        echo "❌ Failed to install pytest"
        exit 1
    }
fi

# Determine test target
if [ -z "$COVERAGE" ]; then
    echo "Running: pytest $TEST_DIR"
    $PYTHON -m pytest "$TEST_DIR" -v --tb=short 2>&1
else
    echo "Running: pytest --cov $TEST_DIR"
    $PYTHON -m pytest "$TEST_DIR" -v --tb=short --cov=. 2>&1
fi

EXIT_CODE=$?
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All tests passed"
else
    echo "❌ Some tests failed (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE