#!/usr/bin/env bash
# Install Mystic Pointer for the current Linux user.
#
#   ./scripts/install.sh
#   curl -fsSL https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/install.sh | bash
#
# Environment overrides:
#   MYSTIC_POINTER_SOURCE   Local checkout, archive URL, or git URL to install
#   MYSTIC_POINTER_REPO     GitHub owner/repository (default: your-username/mystic-pointer)
#   MYSTIC_POINTER_REF      Git ref used for the archive download (default: main)
#   MYSTIC_POINTER_PYTHON   Python interpreter to use (default: python3)
#   MYSTIC_POINTER_HOME     Installation directory (default: ~/.local/share/mystic-pointer)
#   MYSTIC_POINTER_BIN_DIR  Launcher directory (default: ~/.local/bin)

set -euo pipefail

APP_ID="mystic-pointer"
APP_NAME="Mystic Pointer"
DEFAULT_REPO="your-username/mystic-pointer"

REPO="${MYSTIC_POINTER_REPO:-$DEFAULT_REPO}"
REF="${MYSTIC_POINTER_REF:-main}"
PYTHON_BIN="${MYSTIC_POINTER_PYTHON:-python3}"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="${MYSTIC_POINTER_HOME:-$DATA_HOME/mystic-pointer}"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="${MYSTIC_POINTER_BIN_DIR:-$HOME/.local/bin}"
DESKTOP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/256x256/apps"

say() {
    printf '  %s\n' "$*"
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

# Prefer the checkout that contains this script.  When the script is piped from
# curl there is no checkout, so pip downloads the release archive instead.
SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    CANDIDATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
    if [[ -n "$CANDIDATE" && -f "$CANDIDATE/../pyproject.toml" ]]; then
        SCRIPT_DIR="$(cd "$CANDIDATE/.." && pwd)"
    fi
fi

if [[ -n "${MYSTIC_POINTER_SOURCE:-}" ]]; then
    SOURCE="$MYSTIC_POINTER_SOURCE"
elif [[ -n "$SCRIPT_DIR" ]]; then
    SOURCE="$SCRIPT_DIR"
else
    SOURCE="https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"
fi

command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "Python 3.10+ was not found. Install Python and try again."
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
    || fail "Python 3.10+ is required."

say "Installing $APP_NAME into $INSTALL_DIR"

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

# A fresh environment keeps upgrades predictable and makes uninstall a single
# directory removal.
if [[ -d "$VENV_DIR" ]]; then
    rm -rf "$VENV_DIR"
fi
if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    fail "Could not create a virtual environment. On Debian/Ubuntu install python3-venv and try again."
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip
if ! "$VENV_DIR/bin/python" -m pip install "$SOURCE"; then
    fail "Could not install Mystic Pointer. Check your network connection and Python version."
fi

cat > "$BIN_DIR/$APP_ID" <<EOF
#!/usr/bin/env sh
exec "$VENV_DIR/bin/python" -m mystic_pointer.app "\$@"
EOF
chmod +x "$BIN_DIR/$APP_ID"

cat > "$DESKTOP_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Screen-aware AI assistant
Exec="$BIN_DIR/$APP_ID"
Icon=$APP_ID
Terminal=false
Categories=Utility;
Keywords=AI;screenshot;OCR;assistant;
StartupNotify=false
StartupWMClass=MysticPointer
EOF
chmod +x "$DESKTOP_DIR/$APP_ID.desktop"

# Use the app's own pointer mark for the desktop icon.
QT_QPA_PLATFORM=offscreen "$VENV_DIR/bin/python" - "$ICON_DIR/$APP_ID.png" <<'PY' || true
import sys

from PySide6.QtWidgets import QApplication

from mystic_pointer.ui.icons import make_pointer_pixmap
from mystic_pointer.ui.style import ACCENT

app = QApplication([])
pixmap = make_pointer_pixmap(256, color="#ffffff", background=ACCENT, radius=56)
if not pixmap.save(sys.argv[1], "PNG"):
    raise SystemExit(1)
PY

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

say "Installed."
say "Launch Mystic Pointer from your app menu or run: $APP_ID"

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        say "Add $BIN_DIR to PATH to run '$APP_ID' from a terminal."
        ;;
esac
