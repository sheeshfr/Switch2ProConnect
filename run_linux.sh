#!/usr/bin/env bash
# Switch2ProConnect - Linux Application Launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/../Switch2ProConnect.sh" ]; then
    exec "$SCRIPT_DIR/../Switch2ProConnect.sh" "$@"
fi

if [ -f "$SCRIPT_DIR/Switch2ProConnect.sh" ]; then
    exec "$SCRIPT_DIR/Switch2ProConnect.sh" "$@"
fi

cd "$SCRIPT_DIR"
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

export PYTHONPATH="$SCRIPT_DIR/src:$PYTHONPATH"
exec python3 src/gui.py "$@"
