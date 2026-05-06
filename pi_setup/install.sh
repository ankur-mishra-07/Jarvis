#!/bin/bash
# =============================================================================
# J.A.R.V.I.S. Raspberry Pi 5 Installation Script
# One-shot installer: system deps, Ollama, Python venv, audio config, systemd
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# Tested on: Raspberry Pi 5 (8GB) with Raspberry Pi OS Bookworm 64-bit Lite
# =============================================================================

set -euo pipefail

# --- Configuration -----------------------------------------------------------
JARVIS_DIR="/home/pi/Jarvis"
VENV_DIR="$JARVIS_DIR/venv"
OLLAMA_MODEL="mistral:7b-instruct-v0.3-q4_K_M"
PYTHON="python3"
SERVICE_NAME="jarvis"
PI_SETUP_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_step() { echo -e "\n${CYAN}[$1/$TOTAL_STEPS]${NC} $2"; }
log_ok()   { echo -e "  ${GREEN}OK:${NC} $1"; }
log_warn() { echo -e "  ${YELLOW}WARN:${NC} $1"; }
log_err()  { echo -e "  ${RED}ERROR:${NC} $1"; }

TOTAL_STEPS=9

echo "=============================================="
echo "  J.A.R.V.I.S. Raspberry Pi 5 Installer"
echo "=============================================="
echo

# --- Pre-flight checks -------------------------------------------------------
if [ "$(uname -m)" != "aarch64" ]; then
    log_err "This script is designed for ARM64 (aarch64). Detected: $(uname -m)"
    exit 1
fi

if [ "$EUID" -eq 0 ]; then
    log_err "Do not run as root. Run as the 'pi' user (the script uses sudo where needed)."
    exit 1
fi

# =============================================================================
# STEP 1: System package update
# =============================================================================
log_step 1 "Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
log_ok "System updated."

# =============================================================================
# STEP 2: Install system dependencies
# =============================================================================
log_step 2 "Installing system dependencies..."
sudo apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    portaudio19-dev \
    libportaudio2 \
    libasound2-dev \
    libatlas-base-dev \
    libopenblas-dev \
    libffi-dev \
    libssl-dev \
    espeak-ng \
    espeak-ng-data \
    sox \
    libsox-fmt-all \
    alsa-utils \
    flac \
    ffmpeg \
    git \
    curl \
    wget \
    i2c-tools \
    tesseract-ocr \
    libtesseract-dev \
    build-essential

log_ok "System dependencies installed."

# Verify key tools
echo "  Checking installed tools:"
echo -n "    Python: "; python3 --version
echo -n "    espeak-ng: "; espeak-ng --version 2>&1 | head -1 || echo "not found"
echo -n "    sox: "; sox --version 2>&1 | head -1 || echo "not found"
echo -n "    ffmpeg: "; ffmpeg -version 2>&1 | head -1 || echo "not found"
echo -n "    arecord: "; arecord --version 2>&1 | head -1 || echo "not found"

# =============================================================================
# STEP 3: Install ReSpeaker 2-Mic HAT drivers
# =============================================================================
log_step 3 "Installing ReSpeaker 2-Mic HAT drivers..."

# The seeed-voicecard driver from the official repo
if [ ! -d "/home/pi/seeed-voicecard" ]; then
    cd /home/pi
    git clone https://github.com/HinTak/seeed-voicecard.git
    cd seeed-voicecard
    # Use the branch compatible with newer kernels (Pi 5 / Bookworm)
    git checkout v6.6 2>/dev/null || git checkout master
    sudo ./install.sh
    log_ok "ReSpeaker drivers installed (reboot required to activate)."
    log_warn "After this script finishes, reboot the Pi for audio drivers to load."
else
    log_ok "ReSpeaker drivers already installed."
fi

cd "$PI_SETUP_DIR"

# =============================================================================
# STEP 4: Configure ALSA audio
# =============================================================================
log_step 4 "Configuring ALSA audio (ReSpeaker mic + speaker output)..."

# Back up existing config
if [ -f /etc/asound.conf ]; then
    sudo cp /etc/asound.conf /etc/asound.conf.backup.$(date +%Y%m%d)
    log_ok "Backed up existing /etc/asound.conf"
fi

# Install our ALSA config
sudo cp "$PI_SETUP_DIR/asound.conf" /etc/asound.conf
log_ok "ALSA config installed to /etc/asound.conf"

# Add the pi user to the audio group
sudo usermod -aG audio,gpio,i2c pi 2>/dev/null || true
log_ok "User 'pi' added to audio, gpio, i2c groups."

echo
echo "  Audio test commands (run after reboot when ReSpeaker is active):"
echo "    List capture devices:   arecord -l"
echo "    List playback devices:  aplay -l"
echo "    Test recording (5s):    arecord -d 5 -f S16_LE -r 16000 /tmp/test.wav"
echo "    Test playback:          aplay /tmp/test.wav"
echo "    Test espeak:            espeak-ng 'Jarvis online. All systems nominal.'"

# =============================================================================
# STEP 5: Install Ollama
# =============================================================================
log_step 5 "Installing Ollama for ARM64..."

if command -v ollama &>/dev/null; then
    log_ok "Ollama already installed: $(ollama --version 2>&1 || echo 'version unknown')"
else
    curl -fsSL https://ollama.com/install.sh | sh
    log_ok "Ollama installed."
fi

# Enable and start Ollama service
sudo systemctl enable ollama 2>/dev/null || true
sudo systemctl start ollama 2>/dev/null || true

# Wait for Ollama to be ready
echo "  Waiting for Ollama to start..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        log_ok "Ollama is running."
        break
    fi
    sleep 2
done

# =============================================================================
# STEP 6: Pull Ollama model
# =============================================================================
log_step 6 "Pulling Ollama model: $OLLAMA_MODEL (this may take 10-20 minutes)..."

if ollama list 2>/dev/null | grep -q "mistral:7b-instruct"; then
    log_ok "Model already downloaded."
else
    ollama pull "$OLLAMA_MODEL"
    log_ok "Model downloaded."
fi

# Verify
echo "  Installed models:"
ollama list 2>/dev/null || echo "  (could not list models)"

# =============================================================================
# STEP 7: Copy Jarvis code and set up Python virtual environment
# =============================================================================
log_step 7 "Setting up Jarvis code and Python virtual environment..."

# Create Jarvis directory if it doesn't exist
mkdir -p "$JARVIS_DIR"

# If we are running from the pi_setup dir inside the repo, copy the parent
REPO_DIR="$(dirname "$PI_SETUP_DIR")"
if [ -f "$REPO_DIR/jarvis.py" ] && [ "$REPO_DIR" != "$JARVIS_DIR" ]; then
    echo "  Copying Jarvis code from $REPO_DIR to $JARVIS_DIR..."
    # Copy everything except venv, __pycache__, .git, pi_setup
    rsync -a --exclude='venv' --exclude='__pycache__' --exclude='.git' \
          --exclude='pi_setup' --exclude='.DS_Store' \
          "$REPO_DIR/" "$JARVIS_DIR/"
    log_ok "Code copied to $JARVIS_DIR"
elif [ -f "$JARVIS_DIR/jarvis.py" ]; then
    log_ok "Jarvis code already present at $JARVIS_DIR"
else
    log_warn "No Jarvis source found. Copy your Jarvis code to $JARVIS_DIR manually."
fi

# Install Pi-optimized config
cp "$PI_SETUP_DIR/config_pi.json" "$JARVIS_DIR/config.json"
log_ok "Pi-optimized config.json installed."

# Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
    log_ok "Virtual environment created."
else
    log_ok "Virtual environment already exists."
fi

# Install Python dependencies
echo "  Installing Python packages (this may take several minutes on Pi)..."
source "$VENV_DIR/bin/activate"

pip install --upgrade pip setuptools wheel -q

# Core dependencies
pip install \
    SpeechRecognition>=3.10.0 \
    PyAudio>=0.2.14 \
    requests>=2.31.0 \
    numpy \
    scipy \
    noisereduce \
    openai-whisper \
    anthropic>=0.40.0 \
    -q 2>&1 | tail -5

# Pi-specific: skip PyQt6 (not available/needed headless), install pyttsx3 as TTS fallback
pip install pyttsx3 -q 2>/dev/null || log_warn "pyttsx3 not installed (optional)"

deactivate

log_ok "Python dependencies installed."

# Verify key packages
echo "  Verifying Python packages:"
"$VENV_DIR/bin/python3" -c "
import speech_recognition; print(f'    SpeechRecognition: {speech_recognition.__version__}')
import pyaudio; print(f'    PyAudio: {pyaudio.__version__}')
import numpy; print(f'    NumPy: {numpy.__version__}')
import whisper; print(f'    Whisper: OK')
print('    All core packages verified.')
" 2>&1 || log_warn "Some packages may need manual installation."

# =============================================================================
# STEP 8: Install systemd service
# =============================================================================
log_step 8 "Setting up systemd service for auto-start on boot..."

# Stop existing service if running
sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true

# Install the service file
sudo cp "$PI_SETUP_DIR/jarvis.service" /etc/systemd/system/jarvis.service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
log_ok "Jarvis service installed and enabled."

echo
echo "  Service commands:"
echo "    Start:    sudo systemctl start jarvis"
echo "    Stop:     sudo systemctl stop jarvis"
echo "    Restart:  sudo systemctl restart jarvis"
echo "    Status:   sudo systemctl status jarvis"
echo "    Logs:     journalctl -u jarvis -f"

# =============================================================================
# STEP 9: Performance tuning for Pi 5
# =============================================================================
log_step 9 "Applying performance optimizations..."

# Increase swap to 2GB (helps with Ollama + Whisper memory pressure)
SWAP_FILE="/etc/dphys-swapfile"
if [ -f "$SWAP_FILE" ]; then
    CURRENT_SWAP=$(grep "^CONF_SWAPSIZE=" "$SWAP_FILE" | cut -d= -f2)
    if [ "${CURRENT_SWAP:-0}" -lt 2048 ]; then
        sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' "$SWAP_FILE"
        sudo systemctl restart dphys-swapfile 2>/dev/null || true
        log_ok "Swap increased to 2GB."
    else
        log_ok "Swap already >= 2GB."
    fi
fi

# Set GPU memory low (headless — no display needed)
CONFIG_TXT="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_TXT" ]; then
    CONFIG_TXT="/boot/config.txt"
fi
if [ -f "$CONFIG_TXT" ]; then
    if ! grep -q "^gpu_mem=16" "$CONFIG_TXT"; then
        echo "" | sudo tee -a "$CONFIG_TXT" >/dev/null
        echo "# Jarvis: minimize GPU memory for headless operation" | sudo tee -a "$CONFIG_TXT" >/dev/null
        echo "gpu_mem=16" | sudo tee -a "$CONFIG_TXT" >/dev/null
        log_ok "GPU memory set to 16MB (headless mode)."
    else
        log_ok "GPU memory already minimized."
    fi

    # Enable I2C (needed for ReSpeaker HAT)
    if ! grep -q "^dtparam=i2c_arm=on" "$CONFIG_TXT"; then
        echo "dtparam=i2c_arm=on" | sudo tee -a "$CONFIG_TXT" >/dev/null
        log_ok "I2C enabled."
    fi

    # Enable SPI (some ReSpeaker HATs need it)
    if ! grep -q "^dtparam=spi=on" "$CONFIG_TXT"; then
        echo "dtparam=spi=on" | sudo tee -a "$CONFIG_TXT" >/dev/null
        log_ok "SPI enabled."
    fi
fi

# Disable unnecessary services to free resources
echo "  Disabling unnecessary services for headless operation..."
for svc in bluetooth avahi-daemon triggerhappy; do
    if systemctl is-enabled "$svc" 2>/dev/null | grep -q "enabled"; then
        sudo systemctl disable "$svc" 2>/dev/null || true
        sudo systemctl stop "$svc" 2>/dev/null || true
        log_ok "Disabled $svc"
    fi
done

# =============================================================================
# DONE
# =============================================================================
echo
echo "=============================================="
echo -e "  ${GREEN}Installation Complete!${NC}"
echo "=============================================="
echo
echo "  IMPORTANT: Reboot the Pi to activate:"
echo "    - ReSpeaker audio drivers"
echo "    - I2C/SPI interfaces"
echo "    - Swap and GPU memory changes"
echo "    - Jarvis auto-start service"
echo
echo "  Run:  sudo reboot"
echo
echo "  After reboot, verify:"
echo "    1. Audio:   arecord -l && aplay -l"
echo "    2. Ollama:  ollama list"
echo "    3. Jarvis:  sudo systemctl status jarvis"
echo "    4. Logs:    journalctl -u jarvis -f"
echo
echo "  To test audio before reboot:"
echo "    espeak-ng 'Jarvis online. All systems nominal.'"
echo
echo "  To run Jarvis manually (for debugging):"
echo "    cd $JARVIS_DIR"
echo "    source venv/bin/activate"
echo "    QT_QPA_PLATFORM=offscreen python3 jarvis.py"
echo
