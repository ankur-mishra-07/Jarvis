#!/bin/bash
# J.A.R.V.I.S. macOS system setup — auto-start + permission triggers.
# Run once:  bash macos_setup/install_macos.sh

set -e
JARVIS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$JARVIS_DIR/macos_setup/com.jarvis.assistant.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.jarvis.assistant.plist"

echo "=================================================="
echo "  J.A.R.V.I.S. macOS Setup"
echo "=================================================="

# 1. Logs directory
mkdir -p "$JARVIS_DIR/logs"

# 2. Install LaunchAgent (auto-start at login, restart on crash)
mkdir -p "$HOME/Library/LaunchAgents"
# Rewrite paths in the plist to match this machine
sed "s|/Users/ankmishr4/Jarvis|$JARVIS_DIR|g" "$PLIST_SRC" > "$PLIST_DST"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"
echo "  [✓] LaunchAgent installed — Jarvis starts at login and restarts on crash"

# 3. Trigger permission prompts so they appear in System Settings
echo ""
echo "  Triggering macOS permission prompts..."

# Microphone — prompt appears on first mic access (Jarvis will trigger it)
# Screen Recording — trigger via screencapture
screencapture -x /tmp/jarvis_perm_test.jpg 2>/dev/null || true
rm -f /tmp/jarvis_perm_test.jpg

# Automation — trigger via osascript
osascript -e 'tell application "System Events" to get name of first process' >/dev/null 2>&1 || true

echo ""
echo "=================================================="
echo "  MANUAL STEPS (one time, required)"
echo "=================================================="
echo ""
echo "  Open System Settings → Privacy & Security, and in EACH"
echo "  of these sections add/enable BOTH 'Terminal' and 'python3'"
echo "  (python3 lives at: $(which python3))"
echo ""
echo "   1. Microphone        → needed for voice commands"
echo "   2. Accessibility     → needed for clicks & keystrokes (cliclick)"
echo "   3. Screen Recording  → needed for read-screen & click-by-text OCR"
echo "   4. Automation        → allow control of System Events, Chrome, Safari"
echo ""
echo "  TIP: If a section doesn't list python3, click '+' and press"
echo "  Cmd+Shift+G in the file dialog, then paste: $(which python3)"
echo ""
echo "  Useful commands:"
echo "    launchctl unload $PLIST_DST   # stop auto-start"
echo "    launchctl load $PLIST_DST     # re-enable"
echo "    tail -f $JARVIS_DIR/logs/jarvis_stdout.log  # watch logs"
echo ""
echo "  Jarvis is now running in --dual mode (voice + API server)."
echo "=================================================="
