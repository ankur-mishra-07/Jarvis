#!/bin/bash
# ─────────────────────────────────────────────────────────────
# J.A.R.V.I.S. Setup Script
# Installs dependencies and configures auto-start on macOS
# Singleton: safe to re-run — kills old instances automatically
# ─────────────────────────────────────────────────────────────

set -e

JARVIS_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="python3"
PLIST_NAME="com.jarvis.assistant.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
PID_FILE="/tmp/jarvis_assistant.pid"

echo "======================================"
echo "  J.A.R.V.I.S. Setup"
echo "======================================"
echo

# Kill any running Jarvis instances
echo "[0/5] Stopping any running Jarvis instances..."
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$OLD_PID" 2>/dev/null || true
        echo "  Killed previous instance (PID $OLD_PID)."
    fi
    rm -f "$PID_FILE"
fi
# Also kill by process name as fallback
pkill -f "python.*jarvis.py" 2>/dev/null || true
launchctl unload "$PLIST_PATH" 2>/dev/null || true

# Step 1: Install portaudio + sox
echo "[1/5] Installing system dependencies via Homebrew..."
if command -v brew &>/dev/null; then
    brew install portaudio sox 2>/dev/null || echo "  Already installed."
else
    echo "  ERROR: Homebrew not found. Install it from https://brew.sh"
    exit 1
fi

# Step 2: Create virtual environment
echo "[2/5] Setting up Python virtual environment..."
if [ ! -d "$JARVIS_DIR/venv" ]; then
    $PYTHON -m venv "$JARVIS_DIR/venv"
    echo "  Virtual environment created."
else
    echo "  Virtual environment already exists."
fi

# Step 3: Install Python dependencies
echo "[3/5] Installing Python dependencies..."
source "$JARVIS_DIR/venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$JARVIS_DIR/requirements.txt" -q
pip install pyobjc-framework-Cocoa -q 2>/dev/null || echo "  PyObjC optional — skipping."
echo "  Dependencies installed."

# Step 4: Grant microphone and accessibility permissions
echo "[4/5] Checking permissions..."
# Request microphone access by doing a quick test
$JARVIS_DIR/venv/bin/python3 -c "
import speech_recognition as sr
try:
    m = sr.Microphone()
    print('  Microphone access: OK')
except Exception as e:
    print(f'  Microphone: needs permission — {e}')
" 2>/dev/null || echo "  Microphone check skipped."

# Step 5: Create LaunchAgent for auto-start (agent app with KeepAlive)
echo "[5/5] Setting up auto-start on login..."
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jarvis.assistant</string>

    <key>ProgramArguments</key>
    <array>
        <string>$JARVIS_DIR/venv/bin/python3</string>
        <string>$JARVIS_DIR/jarvis.py</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>5</integer>

    <key>ProcessType</key>
    <string>Interactive</string>

    <key>LegacyTimers</key>
    <true/>

    <key>Nice</key>
    <integer>-5</integer>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/jarvis.log</string>

    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/jarvis_error.log</string>

    <key>WorkingDirectory</key>
    <string>$JARVIS_DIR</string>
</dict>
</plist>
PLIST

launchctl load "$PLIST_PATH"

echo
echo "======================================"
echo "  Setup complete!"
echo "======================================"
echo
echo "  Jarvis is now a system background app:"
echo "    - Starts automatically on login"
echo "    - Auto-restarts if it crashes"
echo "    - No dock icon, no Cmd+Tab entry"
echo "    - Always-on microphone (no timeouts)"
echo "    - Single instance (duplicates auto-killed)"
echo
echo "  Commands:"
echo "    Start now:    cd $JARVIS_DIR && source venv/bin/activate && python jarvis.py"
echo "    Stop:         launchctl unload $PLIST_PATH"
echo "    Restart:      launchctl unload $PLIST_PATH && launchctl load $PLIST_PATH"
echo "    View logs:    tail -f ~/Library/Logs/jarvis.log"
echo
echo "  IMPORTANT: Grant microphone access to your terminal/Python in"
echo "  System Settings > Privacy & Security > Microphone"
echo
