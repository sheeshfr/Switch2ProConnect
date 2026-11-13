#!/usr/bin/env bash
# Switch2ProConnect - Linux Setup & Dependency Installation Script
set -e

echo "=== Switch2ProConnect Linux Setup ==="

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "[!] Error: python3 is not installed. Please install Python 3 (>= 3.10) using your package manager."
    exit 1
fi

# Check Python Tkinter
if ! python3 -c "import tkinter" &>/dev/null; then
    echo "[!] Warning: python3-tk is not installed."
    echo "    On Ubuntu/Debian: sudo apt install python3-tk"
    echo "    On Arch/Manjaro:  sudo pacman -S tk"
    echo "    On Fedora:        sudo dnf install python3-tkinter"
fi

# Create virtual environment if requested or install dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

echo "[*] Activating virtual environment..."
source .venv/bin/activate

echo "[*] Upgrading pip..."
pip install --upgrade pip

echo "[*] Installing Linux dependencies..."
pip install -r requirements-linux.txt

# Install udev rules
UDEV_RULE_SRC="$SCRIPT_DIR/resources/99-switch2.rules"
UDEV_DEST="/etc/udev/rules.d/99-switch2.rules"

if [ -f "$UDEV_RULE_SRC" ]; then
    echo ""
    echo "[*] Switch 2 controller udev rules allow non-root access to /dev/uinput and controllers."
    read -p "    Do you want to install udev rules to $UDEV_DEST? [Y/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        sudo cp "$UDEV_RULE_SRC" "$UDEV_DEST"
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        sudo modprobe uinput || true
        # Add user to input group if needed
        sudo usermod -aG input "$USER" || true
        echo "[+] udev rules installed successfully."
        echo "    NOTE: You may need to log out and back in for group changes to take full effect."
    fi
fi

echo ""
echo "=== Setup Complete! ==="
echo "You can launch the app by running: ./run_linux.sh"
