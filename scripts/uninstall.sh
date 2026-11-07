#!/usr/bin/env bash
# Uninstall Mystic Pointer for the current Linux user.
#
#   ./scripts/uninstall.sh
#   curl -fsSL https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/your-username/mystic-pointer/main/scripts/uninstall.sh | bash -s -- --purge
#
# By default the configuration and API keys are preserved.  Pass --purge to
# remove them as well.  Saved screenshots are never deleted.

set -euo pipefail

APP_ID="mystic-pointer"
APP_NAME="Mystic Pointer"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
INSTALL_DIR="${MYSTIC_POINTER_HOME:-$DATA_HOME/mystic-pointer}"
VENV_DIR="$INSTALL_DIR/venv"
BIN_DIR="${MYSTIC_POINTER_BIN_DIR:-$HOME/.local/bin}"
DESKTOP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/256x256/apps"

PURGE=0
for argument in "$@"; do
    case "$argument" in
        --purge)
            PURGE=1
            ;;
        -h|--help)
            printf 'Usage: %s [--purge]\n' "$0"
            printf '  --purge  Also remove configuration, API keys, and caches.\n'
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n' "$argument" >&2
            printf 'Usage: %s [--purge]\n' "$0" >&2
            exit 2
            ;;
    esac
done

say() {
    printf '  %s\n' "$*"
}

# Remove the GNOME system shortcut while the installed package is still
# available.  Failure here must not block the uninstall.
if command -v gsettings >/dev/null 2>&1 && [[ -x "$VENV_DIR/bin/python" ]]; then
    "$VENV_DIR/bin/python" -c \
        'from mystic_pointer.shortcut import uninstall_gnome_shortcut; uninstall_gnome_shortcut()' \
        >/dev/null 2>&1 || true
fi

rm -f "$BIN_DIR/$APP_ID"
rm -f "$DESKTOP_DIR/$APP_ID.desktop"
rm -f "$ICON_DIR/$APP_ID.png"
rm -rf "$INSTALL_DIR"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

if [[ "$PURGE" -eq 1 ]]; then
    rm -rf "$CONFIG_HOME/mystic_pointer"
    rm -rf "$CACHE_HOME/mystic_pointer"
    rm -rf "${TMPDIR:-/tmp}/mystic_pointer_clipboard"
    say "Removed configuration, API keys, and caches."
else
    say "Configuration and API keys were kept."
    say "Run with --purge to remove them too."
fi

say "$APP_NAME has been uninstalled."
