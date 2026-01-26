#!/bin/bash
# AutoBuildr Development Environment Setup
# ========================================
# This script sets up and starts the development environment for AutoBuildr.
#
# Requirements:
#   - Python 3.11+
#   - Node.js 18+
#   - Claude CLI (for agent execution)
#   - ANTHROPIC_API_KEY environment variable
#
# Usage:
#   ./init.sh           # Full setup + start servers
#   ./init.sh --install # Install dependencies only
#   ./init.sh --start   # Start servers only (skip install)

set -e

cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  AutoBuildr Development Environment"
echo "========================================"
echo ""

# Parse arguments
INSTALL_ONLY=false
START_ONLY=false

for arg in "$@"; do
    case $arg in
        --install)
            INSTALL_ONLY=true
            shift
            ;;
        --start)
            START_ONLY=true
            shift
            ;;
    esac
done

# =============================================================================
# CHECK PREREQUISITES
# =============================================================================

echo "[1/6] Checking prerequisites..."

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python not found. Please install Python 3.11+ from https://python.org"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  [OK] Python $PYTHON_VERSION found"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not found. Please install Node.js 18+ from https://nodejs.org"
    exit 1
fi
NODE_VERSION=$(node --version)
echo "  [OK] Node.js $NODE_VERSION found"

# Check npm
if ! command -v npm &> /dev/null; then
    echo "[ERROR] npm not found. It should come with Node.js installation."
    exit 1
fi
echo "  [OK] npm found"

# Check Claude CLI (optional but recommended)
if command -v claude &> /dev/null; then
    echo "  [OK] Claude CLI found"
else
    echo "  [!] Claude CLI not found (optional for dev)"
    echo "      Install from: https://claude.ai/download"
fi

# Check for Anthropic API key
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "  [OK] ANTHROPIC_API_KEY is set"
else
    echo "  [!] ANTHROPIC_API_KEY not set"
    echo "      Set it in your shell: export ANTHROPIC_API_KEY=your-key"
fi

echo ""

# =============================================================================
# SETUP PYTHON VIRTUAL ENVIRONMENT
# =============================================================================

if [ "$START_ONLY" = false ]; then
    echo "[2/6] Setting up Python virtual environment..."

    # Create venv if it doesn't exist or is incompatible
    if [ ! -f "venv/bin/activate" ]; then
        if [ -d "venv" ]; then
            echo "  Removing incompatible virtual environment..."
            rm -rf venv
        fi
        echo "  Creating virtual environment..."
        $PYTHON_CMD -m venv venv
        if [ $? -ne 0 ]; then
            echo "[ERROR] Failed to create virtual environment"
            echo "  Ubuntu/Debian: sudo apt install python3-venv"
            exit 1
        fi
    fi

    # Activate venv
    source venv/bin/activate
    echo "  [OK] Virtual environment activated"

    # =============================================================================
    # INSTALL PYTHON DEPENDENCIES
    # =============================================================================

    echo ""
    echo "[3/6] Installing Python dependencies..."

    # Prefer uv if available for faster installs
    if command -v uv &> /dev/null; then
        echo "  Using uv for fast installation..."
        uv pip install -r requirements.txt
    else
        pip install --upgrade pip --quiet
        pip install -r requirements.txt --quiet
    fi
    echo "  [OK] Python dependencies installed"

    # =============================================================================
    # INSTALL NODE.JS DEPENDENCIES
    # =============================================================================

    echo ""
    echo "[4/6] Installing Node.js dependencies..."

    cd ui
    if [ -f "pnpm-lock.yaml" ]; then
        if command -v pnpm &> /dev/null; then
            pnpm install --silent
        else
            npm install --silent
        fi
    else
        npm install --silent
    fi
    cd ..
    echo "  [OK] Node.js dependencies installed"

    # =============================================================================
    # BUILD FRONTEND (Production)
    # =============================================================================

    echo ""
    echo "[5/6] Building frontend..."
    cd ui
    npm run build
    cd ..
    echo "  [OK] Frontend built"

else
    # Start only mode - just activate venv
    source venv/bin/activate
    echo "[2-5/6] Skipped installation (--start mode)"
fi

if [ "$INSTALL_ONLY" = true ]; then
    echo ""
    echo "[6/6] Installation complete!"
    echo ""
    echo "To start the servers, run:"
    echo "  ./init.sh --start"
    echo ""
    exit 0
fi

# =============================================================================
# START DEVELOPMENT SERVERS
# =============================================================================

echo ""
echo "[6/6] Starting development servers..."
echo ""
echo "========================================"
echo "  Server Information"
echo "========================================"
echo ""
echo "  Backend API:    http://localhost:8888"
echo "  Frontend Dev:   http://localhost:5173 (if running dev mode)"
echo "  WebSocket:      ws://localhost:8888/ws"
echo ""
echo "  To run frontend in dev mode:"
echo "    cd ui && npm run dev"
echo ""
echo "  To view the UI:"
echo "    Open http://localhost:8888 in your browser"
echo ""
echo "========================================"
echo ""

# Start the backend server
echo "Starting backend server..."
python start_ui.py

