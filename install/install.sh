#!/bin/sh
# autogovern installer (POSIX shell, uv-first, user-local, idempotent).
# Usage: curl -fsSL https://raw.githubusercontent.com/ashborn-systems/autogovern/main/install/install.sh | sh
set -e

# Detect OS and architecture.
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux*) OS="linux" ;;
    Darwin*) OS="macos" ;;
    *) echo "Unsupported OS: $OS"; exit 1 ;;
esac

case "$ARCH" in
    x86_64|amd64) ARCH="x86_64" ;;
    aarch64|arm64) ARCH="aarch64" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "Detected: $OS/$ARCH"

# Install uv if absent (user-local, no sudo).
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (user-local)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for this session.
    UV_BIN="$HOME/.local/bin"
    export PATH="$UV_BIN:$PATH"
fi

# Install autogovern as a uv tool (user-local, idempotent).
echo "Installing autogovern..."
uv tool install autogovern

# Verify the binary is on PATH.
if ! command -v autogovern >/dev/null 2>&1; then
    UV_BIN="$HOME/.local/bin"
    echo ""
    echo "autogovern is not on your PATH. Add this to your shell profile:"
    echo "  export PATH=\"$UV_BIN:\$PATH\""
    echo ""
    export PATH="$UV_BIN:$PATH"
fi

echo ""
echo "autogovern installed successfully."
echo "Run 'autogovern init' to get started."
