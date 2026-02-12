#!/bin/bash
# Test script for cron jobs
# This simulates what cron will do

set -e  # Exit on error

# Get project directory (parent of scripts/)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=========================================="
echo "CRON JOB TEST"
echo "=========================================="
echo "Time: $(date)"
echo "Directory: $(pwd)"
echo "User: $(whoami)"
echo "Python: $(which python3)"
echo ""

echo "Testing daily update..."
python3 scripts/update_kb_daily.py
DAILY_EXIT=$?
echo "Daily update exit code: $DAILY_EXIT"
echo ""

echo "Testing health check..."
python3 scripts/monitor_kb_health.py
HEALTH_EXIT=$?
echo "Health check exit code: $HEALTH_EXIT"
echo ""

echo "=========================================="
if [ $DAILY_EXIT -eq 0 ] && [ $HEALTH_EXIT -eq 0 ]; then
    echo "✓ ALL TESTS PASSED"
    echo "Cron jobs should work correctly!"
    exit 0
else
    echo "✗ SOME TESTS FAILED"
    echo "Fix issues before setting up cron"
    exit 1
fi
