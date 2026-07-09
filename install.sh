#!/usr/bin/env bash
set -euo pipefail

REPO="biggs-100/tau-biggz"
PACKAGE="tau-biggz"
VERSION="${1:-latest}"

echo "==> Installing $PACKAGE ($VERSION)..."
echo ""

# ── Detect OS ──────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Linux)   ;;
    Darwin)  ;;
    CYGWIN*|MINGW*|MSYS*) OS="windows" ;;
    *)       echo "Unsupported OS: $OS"; exit 1 ;;
esac

# ── Check Python ────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3.12+ is required."
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  macOS: brew install python@3.12"
    echo "  Windows: https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')
if [ "$(echo "$PY_VERSION" | cut -d. -f1)" -lt 3 ] || { [ "$(echo "$PY_VERSION" | cut -d. -f1)" -eq 3 ] && [ "$(echo "$PY_VERSION" | cut -d. -f2)" -lt 12 ]; }; then
    echo "ERROR: Python 3.12+ required, found $PY_VERSION"
    exit 1
fi

# ── Install pipx if missing ─────────────────────────────────────────────
if ! command -v pipx &>/dev/null; then
    echo "==> Installing pipx..."
    if [ "$OS" = "windows" ]; then
        pip install --user pipx
    else
        python3 -m pip install --user pipx 2>/dev/null || {
            sudo apt install -y pipx 2>/dev/null || {
                echo "Install pipx manually: python3 -m pip install --user pipx"
                exit 1
            }
        }
    fi
    python3 -m pipx ensurepath
fi

# ── Remove old/stale installations ──────────────────────────────────────
if pipx list 2>/dev/null | grep -q "$PACKAGE"; then
    echo "==> Removing previous installation..."
    pipx uninstall "$PACKAGE" 2>/dev/null || true
fi
rm -f ~/.local/bin/tau

# ── Install ─────────────────────────────────────────────────────────────
echo "==> Installing $PACKAGE..."
if [ "$VERSION" = "latest" ]; then
    pipx install "$PACKAGE"
else
    pipx install "$PACKAGE==$VERSION"
fi

# ── Verify ──────────────────────────────────────────────────────────────
echo ""
echo "==> Verifying installation..."
TAU_BIN="$HOME/.local/share/pipx/venvs/$PACKAGE/bin/tau"
if [ -f "$TAU_BIN" ]; then
    # Create direct symlink in case PATH is not set
    ln -sf "$TAU_BIN" ~/.local/bin/tau 2>/dev/null || true

    INSTALLED_VERSION=$("$TAU_BIN" --version 2>/dev/null || echo "unknown")
    echo ""
    echo "  ✅ tau-biggz $INSTALLED_VERSION installed!"
    echo ""
    echo "  Quick start:"
    echo "    export OPENCODE_GO_API_KEY=sk-..."
    echo "    tau"
    echo ""
    echo "  More info: https://github.com/$REPO"
else
    echo "  ⚠️  Installed but binary not found at expected path."
    echo "  Try: pipx install $PACKAGE"
fi
