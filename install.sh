#!/usr/bin/env bash
# tau-biggz installer
# Usage: curl -fsSL https://tau-biggz.dev/install.sh | sh
set -euo pipefail

REPO="biggs-100/tau-biggz"
PACKAGE="tau-biggz"
LATEST="0.1.7"

echo ""
echo "  ╔══════════════════════════════╗"
echo "  ║   tau-biggz installer        ║"
echo "  ╚══════════════════════════════╝"
echo ""

# ── Detect OS ──────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in Linux) ;; Darwin) ;; CYGWIN*|MINGW*|MSYS*) OS="windows" ;; *) echo "Unsupported: $OS"; exit 1 ;; esac

# ── Python check ───────────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        MAJOR="${PY_VER%%.*}"
        MINOR="${PY_VER#*.}"
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ❌ Python 3.12+ required."
    echo "     Install: sudo apt install python3 python3-pip python3-venv  (Linux)"
    echo "              brew install python@3.12                           (macOS)"
    echo "              https://www.python.org/downloads/                  (Windows)"
    exit 1
fi
echo "  ✅ Python $PY_VER found"

# ── Remove ANY existing tau installation ───────────────────────────────
echo "  ⏳ Cleaning previous installations..."
# Remove pipx
pipx uninstall "$PACKAGE" 2>/dev/null || true
# Remove pip --user
pip3 uninstall -y "$PACKAGE" 2>/dev/null || true
pip uninstall -y "$PACKAGE" 2>/dev/null || true
# Remove any stray binaries
rm -f /usr/local/bin/tau 2>/dev/null || true
rm -f ~/.local/bin/tau 2>/dev/null || true
rm -f ~/bin/tau 2>/dev/null || true
# Clear pip cache for this package
pip3 cache remove "$PACKAGE" 2>/dev/null || true
pip cache remove "$PACKAGE" 2>/dev/null || true
echo "  ✅ Clean"

# ── Install ────────────────────────────────────────────────────────────
echo "  ⏳ Installing $PACKAGE $LATEST..."

if command -v pipx &>/dev/null; then
    pipx install --force "$PACKAGE==$LATEST" 2>&1 | tail -1
elif command -v pip3 &>/dev/null; then
    pip3 install --user --force-reinstall --no-cache-dir "$PACKAGE==$LATEST" 2>&1 | tail -1
elif command -v pip &>/dev/null; then
    pip install --user --force-reinstall --no-cache-dir "$PACKAGE==$LATEST" 2>&1 | tail -1
else
    echo "  ❌ pip not found"
    exit 1
fi

# ── Show result ────────────────────────────────────────────────────────
echo ""
echo "  ✅ tau-biggz $LATEST installed!"
echo ""
echo "  Quick start:"
echo "    export OPENCODE_GO_API_KEY=sk-..."
echo "    tau"
echo ""
echo "  GitHub: https://github.com/$REPO"
