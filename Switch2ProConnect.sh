#!/usr/bin/env bash
# ============================================================================
# Switch 2 Pro Connect - Linux Launcher & First-Time Setup
# ============================================================================
# Double-clickable all-in-one launcher for Linux users.
# On first run: checks prerequisites, configures .venv-linux, installs udev rules,
#               registers desktop icon, and launches Switch 2 Pro Connect.
# On subsequent runs: verifies setup and instantly starts the application!
# ============================================================================

set -e

# Resolve directory location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/source" ]; then
    BASE_DIR="$SCRIPT_DIR/source"
    ROOT_DIR="$SCRIPT_DIR"
else
    BASE_DIR="$SCRIPT_DIR"
    ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Use Linux-specific virtual environment so dual-boot / shared drives don't conflict
if [ -d "$BASE_DIR/.venv-linux" ]; then
    VENV_DIR="$BASE_DIR/.venv-linux"
elif [ -d "$BASE_DIR/.venv" ] && [ -x "$BASE_DIR/.venv/bin/python3" ]; then
    VENV_DIR="$BASE_DIR/.venv"
else
    VENV_DIR="$BASE_DIR/.venv-linux"
fi

VENV_PY="$VENV_DIR/bin/python3"
REQ_FILE="$BASE_DIR/requirements-linux.txt"
UDEV_RULE_SRC="$BASE_DIR/resources/99-switch2.rules"
UDEV_DEST="/etc/udev/rules.d/99-switch2.rules"
ICON_SRC="$BASE_DIR/resources/images/icon.png"

# Elevation helper (sudo in terminal, pkexec in GUI)
elevate_cmd() {
    if [ -t 0 ] || [ -n "$SSH_TTY" ]; then
        sudo "$@"
    elif command -v pkexec &>/dev/null; then
        pkexec "$@"
    elif command -v sudo &>/dev/null; then
        sudo "$@"
    else
        "$@"
    fi
}

# Quick check if system has completed initial setup
is_setup_done() {
    # 1. Python virtual environment must exist
    if [ ! -x "$VENV_PY" ]; then
        return 1
    fi

    # 2. Key Linux modules must import cleanly
    if ! "$VENV_PY" -c "import evdev, pyudev, bleak, yaml, PIL, imufusion" &>/dev/null; then
        return 1
    fi

    # 3. Udev rules must be installed in system directory
    if [ ! -f "$UDEV_DEST" ]; then
        return 1
    fi

    # 4. /dev/uinput must be accessible
    if [ ! -c /dev/uinput ] || [ ! -w /dev/uinput ]; then
        return 1
    fi

    return 0
}

# ----------------------------------------------------------------------------
# FAST PATH: Setup already done -> launch immediately without terminal or prompts
# ----------------------------------------------------------------------------
if is_setup_done; then
    cd "$BASE_DIR"
    export PYTHONPATH="$BASE_DIR/src:$PYTHONPATH"
    exec "$VENV_PY" src/gui.py "$@"
fi

# ----------------------------------------------------------------------------
# SETUP PATH: First-time setup or missing prerequisites
# ----------------------------------------------------------------------------

# If launched from GUI without an interactive terminal, spawn one so user can view
# setup progress and authenticate for udev rules
if [ ! -t 0 ] && [ "$1" != "--terminal-spawned" ]; then
    for term in konsole gnome-terminal xfce4-terminal mate-terminal lxterminal alacritty kitty foot xterm x-terminal-emulator; do
        if command -v "$term" &>/dev/null; then
            case "$term" in
                konsole)
                    exec "$term" -p tabtitle="Switch 2 Pro Connect Setup" -e bash "$0" --terminal-spawned "$@"
                    ;;
                gnome-terminal|mate-terminal|xfce4-terminal|lxterminal)
                    exec "$term" --title="Switch 2 Pro Connect Setup" -- bash "$0" --terminal-spawned "$@"
                    ;;
                *)
                    exec "$term" -e bash "$0" --terminal-spawned "$@"
                    ;;
            esac
        fi
    done
fi

echo "========================================================================"
echo "            Nintendo Switch 2 Pro Connect - Linux Setup                 "
echo "========================================================================"
echo " Preparing your system for Switch 2 Pro Controller support."
echo " This setup runs automatically on first launch."
echo "========================================================================"
echo ""

# 1. Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "[!] Error: python3 is not installed."
    echo "    Please install Python 3 (>= 3.10) using your package manager."
    read -p "Press Enter to exit..."
    exit 1
fi

# 2. Check Tkinter
if ! python3 -c "import tkinter" &>/dev/null; then
    echo "[!] Notice: python3-tk is required for the user interface."
    echo "    Please install it using your distribution's package manager:"
    echo "    - Ubuntu/Debian/Mint:  sudo apt install python3-tk"
    echo "    - Fedora/Nobara:       sudo dnf install python3-tkinter"
    echo "    - Arch/Manjaro:        sudo pacman -S tk"
    echo ""
fi

# 3. Create Virtual Environment with system site packages (inherits native evdev/tkinter)
if [ ! -d "$VENV_DIR" ] || [ ! -x "$VENV_PY" ]; then
    echo "[*] Creating Python virtual environment in $VENV_DIR..."
    python3 -m venv --system-site-packages "$VENV_DIR"
fi

# 4. Install / Verify pip packages
echo "[*] Installing/verifying Linux requirements (evdev, pyudev, bleak, etc.)..."
"$VENV_DIR/bin/pip" install --upgrade pip 2>/dev/null || true
if ! "$VENV_DIR/bin/pip" install -r "$REQ_FILE" 2>/dev/null; then
    echo "[*] Installing modular packages..."
    "$VENV_DIR/bin/pip" install bleak PyYAML imufusion hidapi pyusb libusb-package numpy pystray Pillow pyserial pyudev python-xlib
fi

# 5. Install udev rules & setup /dev/uinput permissions
if [ ! -f "$UDEV_DEST" ] || [ ! -w /dev/uinput ]; then
    echo ""
    echo "[*] Controller & Force-Feedback Permissions:"
    echo "    Switch 2 Pro Connect requires non-root access to /dev/uinput"
    echo "    and Switch 2 USB/Bluetooth devices to provide rumble and input."
    echo "    Installing $UDEV_DEST..."
    echo ""
    elevate_cmd cp "$UDEV_RULE_SRC" "$UDEV_DEST"
    elevate_cmd udevadm control --reload-rules || true
    elevate_cmd udevadm trigger || true
    elevate_cmd modprobe uinput 2>/dev/null || true
    elevate_cmd usermod -aG input "$USER" 2>/dev/null || true
    echo "[+] udev rules installed successfully."
fi

# 6. Configure Desktop Integration & Icons
echo "[*] Configuring desktop integration..."
USER_ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
mkdir -p "$USER_ICON_DIR" "$HOME/.local/share/icons" 2>/dev/null || true
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$USER_ICON_DIR/switch2proconnect.png" 2>/dev/null || true
    cp "$ICON_SRC" "$HOME/.local/share/icons/switch2proconnect.png" 2>/dev/null || true
    command -v gtk-update-icon-cache &>/dev/null && gtk-update-icon-cache "$HOME/.local/share/icons" 2>/dev/null || true
fi

APP_DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DESKTOP_DIR" 2>/dev/null || true

LAUNCHER_PATH="$ROOT_DIR/Switch2ProConnect.sh"
if [ ! -f "$LAUNCHER_PATH" ]; then
    LAUNCHER_PATH="$BASE_DIR/Switch2ProConnect.sh"
fi

cat <<EOF > "$APP_DESKTOP_DIR/Switch2ProConnect.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=Switch 2 Pro Connect
GenericName=Switch 2 Controller Utility
Comment=Connect and configure Switch 2 Pro Controller
Exec="$LAUNCHER_PATH"
Icon=$ICON_SRC
Terminal=false
Categories=Game;Utility;
StartupNotify=true
StartupWMClass=switch2proconnect
EOF
chmod +x "$APP_DESKTOP_DIR/Switch2ProConnect.desktop" 2>/dev/null || true

# Update desktop files with absolute icon path and mark trusted
for dt in "$ROOT_DIR/Switch2ProConnect.desktop" "$BASE_DIR/Switch2ProConnect.desktop"; do
    if [ -f "$dt" ]; then
        sed -i "s|^Icon=.*|Icon=$ICON_SRC|" "$dt" 2>/dev/null || true
        chmod +x "$dt" 2>/dev/null || true
        command -v gio &>/dev/null && gio set "$dt" metadata::trusted true 2>/dev/null || true
    fi
done

echo ""
echo "========================================================================"
echo " [+] Setup Complete! Launching Switch 2 Pro Connect..."
echo "========================================================================"
sleep 1

cd "$BASE_DIR"
export PYTHONPATH="$BASE_DIR/src:$PYTHONPATH"
exec "$VENV_PY" src/gui.py "$@"
