#!/bin/bash
# Install J.A.R.V.I.S. as a macOS Login Item via AppleScript.
# Unlike LaunchAgent, this runs in the user GUI session and keeps mic access.

set -e

JARVIS_DIR="/Users/ankmishr4/Jarvis"
LAUNCHER="$JARVIS_DIR/jarvis_launcher.command"
LOG_DIR="$JARVIS_DIR/logs"

echo "── J.A.R.V.I.S. Login Item Installer ──"

# 1. Remove any LaunchAgent — it doesn't have mic access
launchctl unload ~/Library/LaunchAgents/com.jarvis.assistant.plist 2>/dev/null || true
rm -f ~/Library/LaunchAgents/com.jarvis.assistant.plist

# 2. Kill any running instance
pkill -9 -f "python.*jarvis.py" 2>/dev/null || true
rm -f /tmp/jarvis_assistant.pid
sleep 1

mkdir -p "$LOG_DIR"

# 3. Create the launcher script that Login Items will run
cat > "$LAUNCHER" <<EOF
#!/bin/bash
# JARVIS launcher — invoked by macOS Login Item
cd "$JARVIS_DIR"
source venv/bin/activate
exec python -u jarvis.py >> "$LOG_DIR/jarvis.out.log" 2>&1
EOF
chmod +x "$LAUNCHER"

# 4. Remove existing Login Item (if any) and add new
osascript <<APPLESCRIPT
tell application "System Events"
    try
        delete login item "jarvis_launcher"
    end try
    try
        delete login item "jarvis_launcher.command"
    end try
    make new login item at end with properties {path:"$LAUNCHER", hidden:true, name:"jarvis_launcher"}
end tell
APPLESCRIPT

# 5. Start it right now
nohup "$LAUNCHER" > /dev/null 2>&1 &
disown
sleep 2

# 6. Verify
if pgrep -f "python.*jarvis.py" > /dev/null; then
    echo "✓ JARVIS running (PID $(pgrep -f 'python.*jarvis.py'))"
    echo "✓ Auto-start registered as Login Item"
    echo ""
    echo "  Will launch automatically at every login"
    echo "  Hidden from dock (LSUIElement=1)"
    echo "  Runs in user session → full mic + audio access"
    echo ""
    echo "  Live log:     tail -f $LOG_DIR/jarvis.out.log"
    echo "  Stop now:     pkill -f 'python.*jarvis.py'"
    echo "  Start again:  $LAUNCHER &"
    echo "  Remove from Login Items: System Settings → General → Login Items"
else
    echo "✗ Failed to start — check $LOG_DIR/jarvis.out.log"
    exit 1
fi
