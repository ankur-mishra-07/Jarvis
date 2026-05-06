#!/bin/bash
# Install J.A.R.V.I.S. as a macOS LaunchAgent
# - Auto-starts on login
# - Restarts automatically if it crashes (KeepAlive)
# - Hidden from Dock and Cmd+Tab (LSUIElement via jarvis.py)
# - Full user-level privileges (access to mic, apps, files, network)
#
# Run:    ./install_service.sh
# Stop:   launchctl unload ~/Library/LaunchAgents/com.jarvis.assistant.plist
# Start:  launchctl load   ~/Library/LaunchAgents/com.jarvis.assistant.plist
# Status: launchctl list | grep jarvis

set -e

JARVIS_DIR="/Users/ankmishr4/Jarvis"
PLIST_NAME="com.jarvis.assistant.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_DIR="$JARVIS_DIR/logs"

echo "── J.A.R.V.I.S. System Service Installer ──"

# 1. Verify Python venv & deps exist
if [ ! -d "$JARVIS_DIR/venv" ]; then
  echo "✗ venv not found at $JARVIS_DIR/venv — run setup.sh first"
  exit 1
fi

# 2. Create log dir
mkdir -p "$LOG_DIR"

# 3. Stop any running instance
echo "→ Stopping any existing Jarvis..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true
pkill -f "python.*jarvis.py" 2>/dev/null || true
rm -f /tmp/jarvis_assistant.pid
sleep 1

# 4. Write the LaunchAgent plist
echo "→ Writing LaunchAgent plist..."
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.jarvis.assistant</string>

    <key>ProgramArguments</key>
    <array>
        <string>$JARVIS_DIR/venv/bin/python</string>
        <string>-u</string>
        <string>$JARVIS_DIR/jarvis.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$JARVIS_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>$HOME</string>
        <key>LANG</key>
        <string>en_US.UTF-8</string>
    </dict>

    <!-- Auto-start at login -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart if it crashes -->
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>

    <!-- Higher priority (slightly elevated, not negative = higher) -->
    <key>Nice</key>
    <integer>-5</integer>

    <!-- Interactive session (needed for GUI, mic, audio) -->
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>LimitLoadToSessionType</key>
    <string>Aqua</string>

    <!-- Logs -->
    <key>StandardOutPath</key>
    <string>$LOG_DIR/jarvis.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/jarvis.err.log</string>

    <!-- Minimum 10 seconds between restart attempts -->
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

echo "→ Plist written to: $PLIST_PATH"

# 5. Load (start) the service
echo "→ Loading LaunchAgent..."
launchctl load -w "$PLIST_PATH"
sleep 2

# 6. Verify it's running
if launchctl list | grep -q com.jarvis.assistant; then
    echo ""
    echo "✓ J.A.R.V.I.S. is installed and running as a background service"
    echo ""
    echo "  Logs:      $LOG_DIR/jarvis.out.log"
    echo "  Errors:    $LOG_DIR/jarvis.err.log"
    echo "  Live log:  tail -f $LOG_DIR/jarvis.out.log"
    echo ""
    echo "  Stop:    launchctl unload $PLIST_PATH"
    echo "  Start:   launchctl load   $PLIST_PATH"
    echo "  Restart: launchctl unload $PLIST_PATH && launchctl load $PLIST_PATH"
    echo ""
    echo "  Jarvis will now auto-start every time you log in."
    echo "  No dock icon. No Cmd+Tab entry. Pure background service."
else
    echo "✗ Failed to load LaunchAgent — check $LOG_DIR/jarvis.err.log"
    exit 1
fi
