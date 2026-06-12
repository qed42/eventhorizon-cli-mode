#!/usr/bin/env bash
# EventHorizon CLI — one-command setup

# Resolve script directory before anything else.
# When sourced, $0 may be the shell itself (bash/zsh) or the script path.
# BASH_SOURCE[0] works in bash; ${(%):-%x} works in zsh; fall back to $0.
if [ -n "${BASH_SOURCE:-}" ]; then
    _eh_script="${BASH_SOURCE}"
elif [ -n "${ZSH_VERSION:-}" ]; then
    _eh_script="${(%):-%x}"
else
    _eh_script="$0"
fi
_eh_dir="$(cd "$(dirname "$_eh_script")" && pwd)"
unset _eh_script

# ── Check for Python 3 ──────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is not installed or not on your PATH."
    echo ""
    echo "Install Python 3.9+ for your platform:"
    echo "  macOS:   brew install python"
    echo "  Ubuntu:  sudo apt install python3 python3-venv"
    echo "  Fedora:  sudo dnf install python3"
    echo "  Windows: https://www.python.org/downloads/"
    echo ""
    echo "Then re-run:  source ./setup.sh"
    unset _eh_dir
    return 1 2>/dev/null || exit 1
fi

# Verify minimum version (3.9)
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
    echo "ERROR: Python 3.9+ is required, but you have Python $PY_VERSION."
    echo ""
    echo "Please upgrade Python and re-run:  source ./setup.sh"
    unset _eh_dir PY_VERSION PY_MAJOR PY_MINOR
    return 1 2>/dev/null || exit 1
fi

echo "Setting up EventHorizon CLI... (Python $PY_VERSION)"

# ── Create venv and install ──────────────────────────────────────
# Use absolute paths throughout — no subshell, no cd needed.

echo "[1/3] Creating virtual environment..."
python3 -m venv "$_eh_dir/.venv"
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create virtual environment."
    unset _eh_dir PY_VERSION PY_MAJOR PY_MINOR
    return 1 2>/dev/null || exit 1
fi

echo "[2/3] Upgrading pip..."
"$_eh_dir/.venv/bin/pip" install --quiet --upgrade pip
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to upgrade pip."
    unset _eh_dir PY_VERSION PY_MAJOR PY_MINOR
    return 1 2>/dev/null || exit 1
fi

echo "[3/3] Installing eventhorizon..."
"$_eh_dir/.venv/bin/pip" install -e "$_eh_dir/.[dev]" --quiet
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install eventhorizon."
    unset _eh_dir PY_VERSION PY_MAJOR PY_MINOR
    return 1 2>/dev/null || exit 1
fi

# Activate the venv in the current shell.
# shellcheck disable=SC1091
source "$_eh_dir/.venv/bin/activate"

echo ""
echo -e "\033[32mSetup complete! Run:"
echo "  eh <path_to_drupal_project>    Analyze a Drupal codebase"
echo -e "  eh --help                      See all options\033[0m"

unset _eh_dir PY_VERSION PY_MAJOR PY_MINOR
