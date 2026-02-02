#!/bin/bash
# init.sh - Repo Concierge Development Environment Setup
# This script sets up and verifies the development environment.

set -e

echo "======================================"
echo " Repo Concierge - Environment Setup"
echo "======================================"
echo ""

# Check Python version
echo "Checking Python version..."
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python is not installed. Please install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "ERROR: Python 3.10+ is required. Found: Python $PYTHON_VERSION"
    exit 1
fi
echo "  Found: Python $PYTHON_VERSION (OK)"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
    echo "  Virtual environment created at .venv/"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install -e . --quiet
echo "  Dependencies installed."

# Verify installation
echo ""
echo "Verifying installation..."
python -c "import repo_concierge; print(f'  repo_concierge v{repo_concierge.__version__} imported successfully')"
python -c "import yaml; print(f'  PyYAML v{yaml.__version__} available')"
python -c "import pytest; print(f'  pytest v{pytest.__version__} available')"

# Create reports directory if missing
mkdir -p reports

echo ""
echo "======================================"
echo " Setup Complete!"
echo "======================================"
echo ""
echo "Usage:"
echo "  source .venv/bin/activate          # Activate venv (if not already)"
echo "  python -m repo_concierge --help    # Show CLI help"
echo "  python -m repo_concierge scan .    # Scan current directory"
echo "  pytest                             # Run test suite"
echo ""
echo "Development:"
echo "  Project structure:"
echo "    repo_concierge/   - Main package (cli, scanner, rules, reporting, models)"
echo "    config/           - Configuration files (command_allowlist.yaml)"
echo "    tests/            - Test suite with fixtures"
echo "    reports/          - Generated report output"
echo ""
