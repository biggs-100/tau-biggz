#!/bin/sh
# tau-biggz installer
# Usage: curl -fsSL https://raw.githubusercontent.com/biggs-100/tau-biggz/main/install.sh | sh
set -eu

REPO="biggs-100/tau-biggz"
PACKAGE="tau-biggz"
LATEST="0.1.7"

echo ""
echo "  tau-biggz installer"
echo ""

# ── Detect OS ──────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in Linux) ;; Darwin) ;; *) echo "Unsupported: $OS"; exit 1 ;; esac

# ── Python check ───────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PY_VER=$("$cmd" --version 2>&1 | awk '{print $2}' | cut -d. -f1-2)
        MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  Python 3.12+ required."
    echo "  Linux: sudo apt install python3 python3-pip python3-venv"
    echo "  macOS: brew install python@3.12"
    exit 1
fi
echo "  Python $PY_VER found"

# ── Clean previous installations ───────────────────────────────────────
echo "  Cleaning..."
pipx uninstall "$PACKAGE" 2>/dev/null || true
"$PYTHON" -m pip uninstall -y "$PACKAGE" 2>/dev/null || true
"$PYTHON" -m pip cache remove "$PACKAGE" 2>/dev/null || true

# Remove old binaries
rm -f /usr/local/bin/tau 2>/dev/null || true
rm -f "$HOME/.local/bin/tau" 2>/dev/null || true

# ── Install ────────────────────────────────────────────────────────────
echo "  Installing $PACKAGE $LATEST..."
if command -v pipx >/dev/null 2>&1; then
    pipx install --force "$PACKAGE==$LATEST" 2>&1 | tail -1
else
    "$PYTHON" -m pip install --user --force-reinstall --no-cache-dir "$PACKAGE==$LATEST"
fi

# ── Ensure ~/.local/bin is in PATH ─────────────────────────────────────
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo ""
    echo "  Add to your shell profile:"
    echo '    export PATH="$HOME/.local/bin:$PATH"'
fi

# ── Show result ────────────────────────────────────────────────────────
echo ""
echo "  tau-biggz $LATEST installed!"
echo ""
echo "  Quick start:"
echo "    export OPENCODE_GO_API_KEY=sk-..."
echo "    tau"
echo ""
echo "  GitHub: https://github.com/$REPO"
