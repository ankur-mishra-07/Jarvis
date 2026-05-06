# J.A.R.V.I.S. on Raspberry Pi 5 -- Complete Setup Guide

Deploy Jarvis as an always-on voice assistant (like Google Home) on a Raspberry Pi 5.

---

## Table of Contents

1. [Hardware Shopping List](#1-hardware-shopping-list)
2. [Flash Raspberry Pi OS](#2-flash-raspberry-pi-os)
3. [Initial Pi Configuration](#3-initial-pi-configuration)
4. [Install System Dependencies](#4-install-system-dependencies)
5. [Install ReSpeaker Mic HAT Drivers](#5-install-respeaker-mic-hat-drivers)
6. [Configure ALSA Audio](#6-configure-alsa-audio)
7. [Configure Speaker Output](#7-configure-speaker-output)
8. [Install Ollama (Local LLM)](#8-install-ollama-local-llm)
9. [Install Python Environment and Whisper](#9-install-python-environment-and-whisper)
10. [Copy Jarvis Code to Pi](#10-copy-jarvis-code-to-pi)
11. [Auto-Start Jarvis on Boot (systemd)](#11-auto-start-jarvis-on-boot-systemd)
12. [Optimization Tips](#12-optimization-tips)
13. [Troubleshooting](#13-troubleshooting)
14. [Quick Start (One-Shot Install)](#14-quick-start-one-shot-install)

---

## 1. Hardware Shopping List

| Item | Recommended | Approx. Price | Notes |
|------|-------------|---------------|-------|
| Raspberry Pi 5 (8GB) | Official RPi 5 8GB | $80 | Must be 8GB for Ollama + Whisper |
| Power Supply | Official USB-C 27W (5.1V/5A) | $12 | Pi 5 needs 5A; do NOT use phone chargers |
| microSD Card | Samsung EVO Plus 64GB+ (A2 class) | $10 | A2 rating important for random I/O speed |
| ReSpeaker Mic HAT | Seeed Studio ReSpeaker 2-Mic HAT | $12 | Fits Pi GPIO header; 2 mics with built-in codec |
| Speaker (option A) | Any 3.5mm powered speaker | $10-20 | Plugs into Pi headphone jack |
| Speaker (option B) | USB speaker/DAC | $15-30 | Better quality; shows as separate ALSA device |
| Case | Official Pi 5 case or Argon ONE | $10-25 | Must allow GPIO access for ReSpeaker HAT |
| Heatsink/Fan | Active cooler for Pi 5 | $5-10 | Essential for sustained Ollama inference |
| Ethernet (optional) | Cat6 cable | $5 | More reliable than WiFi for STT API calls |

**Total: approximately $150-200**

### Alternative Mic Options

- **ReSpeaker 4-Mic Array HAT** ($20) -- Better far-field pickup, same driver install process
- **ReSpeaker USB Mic Array** ($70) -- No HAT driver needed, plug-and-play, best quality
- **USB conference mic** ($20-40) -- Any USB mic works; skip the ReSpeaker driver steps

---

## 2. Flash Raspberry Pi OS

### Download and Flash

1. Download **Raspberry Pi Imager** on your Mac/PC: https://www.raspberrypi.com/software/
2. Insert the microSD card into your computer
3. Open Raspberry Pi Imager and select:
   - **Device:** Raspberry Pi 5
   - **OS:** Raspberry Pi OS (64-bit) Lite -- Bookworm
     - Choose "Raspberry Pi OS (other)" then "Raspberry Pi OS Lite (64-bit)"
     - **Use Lite (no desktop)** since Jarvis runs headless
   - **Storage:** Your microSD card

4. Click the **gear icon** (or "Edit Settings") to pre-configure:
   - **Hostname:** `jarvis`
   - **Enable SSH:** Yes (use password authentication)
   - **Username:** `pi`
   - **Password:** (choose a strong password)
   - **WiFi:** Enter your SSID and password
   - **Locale:** Set your timezone and keyboard layout

5. Click **Write** and wait for it to finish
6. Insert the card into the Pi and power on

### Verify Boot

Wait 60-90 seconds for first boot, then:

```bash
# From your Mac/PC:
ssh pi@jarvis.local
# Or use the IP address:
ssh pi@<ip-address>
```

**Test:** You should get a shell prompt on the Pi.

---

## 3. Initial Pi Configuration

SSH into the Pi and run:

```bash
# Update everything first
sudo apt-get update && sudo apt-get upgrade -y

# Run raspi-config for hardware settings
sudo raspi-config
```

In raspi-config, configure:

1. **System Options > Hostname** -- Set to `jarvis`
2. **Interface Options > I2C** -- Enable (needed for ReSpeaker HAT)
3. **Interface Options > SPI** -- Enable (some ReSpeaker versions need it)
4. **Advanced Options > Expand Filesystem** -- Ensures full SD card is used
5. **Finish** and reboot when prompted

```bash
sudo reboot
```

After reboot, reconnect via SSH and verify:

```bash
# Verify 64-bit ARM
uname -m
# Expected output: aarch64

# Verify filesystem expanded
df -h /
# Should show your full SD card size

# Verify I2C enabled
ls /dev/i2c-*
# Expected output: /dev/i2c-1
```

---

## 4. Install System Dependencies

```bash
sudo apt-get install -y \
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
```

**Test each tool:**

```bash
python3 --version          # Should be 3.11+
espeak-ng "Hello world"   # Should play audio (may need speaker connected)
sox --version              # Should print version
ffmpeg -version            # Should print version
arecord --version          # Should print version
tesseract --version        # Should print version
```

### Why each package?

| Package | Purpose |
|---------|---------|
| `portaudio19-dev` | PyAudio backend (microphone capture) |
| `espeak-ng` | Text-to-speech on Linux (replaces macOS `say` command) |
| `sox` | Audio effects pipeline (voice profiles with pitch/bass) |
| `ffmpeg` | Audio format conversion (Whisper needs it) |
| `flac` | FLAC codec for SpeechRecognition |
| `libatlas-base-dev` | Optimized math for NumPy on ARM |
| `libopenblas-dev` | BLAS library for matrix operations |
| `tesseract-ocr` | OCR for Jarvis tools |
| `alsa-utils` | `arecord`, `aplay`, `amixer` for audio testing |
| `i2c-tools` | Diagnostic tools for ReSpeaker HAT |

---

## 5. Install ReSpeaker Mic HAT Drivers

The ReSpeaker 2-Mic HAT uses a WM8960 audio codec that needs kernel drivers.

### Physical Installation

1. **Power off the Pi:** `sudo shutdown -h now`
2. **Attach the ReSpeaker HAT** to the 40-pin GPIO header (push down firmly)
3. **Power on the Pi** and SSH back in

### Driver Installation

```bash
cd /home/pi
git clone https://github.com/HinTak/seeed-voicecard.git
cd seeed-voicecard

# Use the branch matching your kernel version
# For Pi 5 with Bookworm (kernel 6.6.x):
git checkout v6.6 2>/dev/null || git checkout master

sudo ./install.sh
sudo reboot
```

The HinTak fork is maintained for newer kernels. The original Seeed repo
(https://github.com/respeaker/seeed-voicecard) is abandoned and does not
support kernel 6.x.

### Verify Drivers Loaded

After reboot:

```bash
# Check for the sound card
arecord -l
```

Expected output should include something like:

```
card 1: seeed2micvoicec [seeed-2mic-voicecard], device 0: ...
```

If you see the seeed card, the driver is working.

```bash
# Additional checks:
dmesg | grep -i wm8960          # Should show codec loaded
lsmod | grep snd_soc_wm8960     # Should show module loaded
cat /proc/asound/cards           # Should list both cards
```

### Test Recording

```bash
# Record 5 seconds from the ReSpeaker (adjust card number if needed)
arecord -D plughw:1,0 -f S16_LE -r 16000 -d 5 /tmp/test_mic.wav

# Play it back through the speaker
aplay /tmp/test_mic.wav
```

You should hear your own voice played back. If not, check the card number
with `arecord -l` and adjust.

### For ReSpeaker 4-Mic Array HAT

Same process, same driver repo. The 4-mic version uses the AC108 codec:

```bash
dmesg | grep -i ac108     # Verify 4-mic codec
```

---

## 6. Configure ALSA Audio

The ALSA config routes audio so applications automatically use the right
devices without specifying them each time.

### Install the Config

```bash
# Back up any existing config
sudo cp /etc/asound.conf /etc/asound.conf.bak 2>/dev/null || true

# Copy the Jarvis ALSA config
sudo cp /home/pi/Jarvis/pi_setup/asound.conf /etc/asound.conf
```

### Verify Device Numbers

The config assumes card 0 = headphone jack, card 1 = ReSpeaker. Verify:

```bash
cat /proc/asound/cards
```

If the numbers differ, edit `/etc/asound.conf` and change the `card` numbers.

### Test Default Devices

```bash
# Test that default capture uses the ReSpeaker
arecord -d 3 -f S16_LE -r 16000 /tmp/test_default.wav

# Test that default playback uses the speaker
aplay /tmp/test_default.wav

# Test espeak through the default output
espeak-ng "Audio configuration verified. All systems nominal."
```

---

## 7. Configure Speaker Output

### Option A: 3.5mm Headphone Jack (Simplest)

1. Plug a powered speaker into the Pi 5 headphone jack
2. Test:

```bash
# Set output to headphone jack
amixer -c 0 cset numid=1 1

# Test
espeak-ng "Testing three point five millimeter output."
speaker-test -c 2 -t wav -l 1
```

3. Adjust volume:

```bash
amixer -c 0 set Headphone 80%
```

### Option B: USB Speaker/DAC

1. Plug in the USB speaker
2. Find it:

```bash
aplay -l
# Look for USB Audio device, note the card number
```

3. Edit `/etc/asound.conf` -- change `pcm.speaker` card number to the USB device
4. Test:

```bash
espeak-ng "Testing USB audio output."
```

### Option C: I2S DAC HAT (Best Quality)

If you want high-quality audio and are not using the ReSpeaker HAT for output:

1. Add the DAC overlay to `/boot/firmware/config.txt`:

```
dtoverlay=hifiberry-dac
```

2. Reboot and update ALSA config card numbers

### Volume Control

```bash
# List available controls
amixer -c 0 contents

# Set volume (adjust control name to match your device)
amixer -c 0 set Headphone 85%

# Or use alsamixer for interactive control (over SSH)
alsamixer
```

---

## 8. Install Ollama (Local LLM)

Ollama runs natively on ARM64 and manages model downloads.

### Install

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Enable and Start

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

### Verify

```bash
# Check it's running
curl http://localhost:11434/api/tags
# Should return JSON with "models" key

ollama --version
```

### Pull the Mistral Model

This downloads approximately 4.4GB. On a decent connection it takes 10-20 minutes.

```bash
ollama pull mistral:7b-instruct-v0.3-q4_K_M
```

### Test the Model

```bash
ollama run mistral:7b-instruct-v0.3-q4_K_M "Say hello in one sentence."
```

Expected: A short greeting. Response time on Pi 5 8GB will be 5-15 seconds
for the first token, then streaming.

### Verify Ollama API

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"mistral:7b-instruct-v0.3-q4_K_M","prompt":"Hello","stream":false}' \
  | python3 -m json.tool | head -5
```

### Memory Usage

The q4_K_M quantization uses about 4.5GB RAM. With Whisper tiny.en (~150MB)
and Python overhead, total usage stays under 6GB on the 8GB Pi 5.

```bash
# Monitor memory during inference
watch -n 1 free -h
```

---

## 9. Install Python Environment and Whisper

### Create Virtual Environment

```bash
cd /home/pi/Jarvis
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
```

### Install Python Packages

```bash
pip install \
    SpeechRecognition>=3.10.0 \
    PyAudio>=0.2.14 \
    requests>=2.31.0 \
    numpy \
    scipy \
    noisereduce \
    openai-whisper \
    anthropic>=0.40.0
```

**Note:** `PyQt6` is NOT installed. It is not available for ARM64 and is not
needed in headless mode. The systemd service sets `QT_QPA_PLATFORM=offscreen`
to handle any PyQt6 import attempts gracefully, but the Pi deployment should
bypass the UI entirely.

### Install espeak Python binding (optional)

```bash
pip install pyttsx3
```

### Verify Packages

```bash
python3 -c "
import speech_recognition as sr
print(f'SpeechRecognition: {sr.__version__}')

import pyaudio
print(f'PyAudio: {pyaudio.__version__}')

import numpy
print(f'NumPy: {numpy.__version__}')

import whisper
model = whisper.load_model('tiny.en')
print(f'Whisper tiny.en loaded on: {model.device}')
print('All packages OK.')
"
```

Expected: All packages import successfully, Whisper loads the tiny.en model.
First load downloads the model (~75MB).

### Whisper Model Sizes (Pi 5 Benchmarks)

| Model | Size | RAM | Speed (5s audio) | Accuracy |
|-------|------|-----|-------------------|----------|
| tiny.en | 75MB | ~150MB | ~2s | Good for commands |
| base.en | 140MB | ~300MB | ~5s | Better accuracy |
| small.en | 460MB | ~800MB | ~15s | Too slow for real-time |

**Recommendation:** Use `tiny.en` for the Pi. It handles short commands well.
For better accuracy, rely on Google STT (which Jarvis uses as the primary
wake-word detector anyway) and use Whisper only as a fallback.

---

## 10. Copy Jarvis Code to Pi

### From Your Mac

```bash
# On your Mac, from the Jarvis project root:
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='.git' \
    --exclude='pi_setup' --exclude='.DS_Store' \
    /Users/ankmishr4/Jarvis/ pi@jarvis.local:/home/pi/Jarvis/
```

### Install Pi Config

```bash
# On the Pi:
cp /home/pi/Jarvis/pi_setup/config_pi.json /home/pi/Jarvis/config.json
```

### Key Differences from macOS Config

The `config_pi.json` sets:

- `whisper_model`: `"tiny.en"` (fast enough for Pi CPU)
- `brain_priority`: `["ollama"]` only (no cloud APIs by default)
- `voice_rate`: `170` (slightly slower for speaker clarity)
- `tts_engine`: `"espeak"` (Linux TTS instead of macOS `say`)
- `headless`: `true` (skip UI initialization)

### Code Modifications Needed

The Jarvis codebase has macOS-specific code that needs adaptation for the Pi.
The main changes needed are:

**1. TTS Engine (jarvis.py SpeechEngine class)**

The `SpeechEngine` class uses macOS `say` and `afplay`. On Pi, it must use
`espeak-ng` and `aplay`. You will need to modify the `speak` method:

```python
# Pi-compatible speak method concept:
import platform
import subprocess

def speak(self, text):
    if platform.system() == "Linux":
        # Use espeak-ng on Linux/Pi
        rate = str(self._rate)
        subprocess.run(
            ["espeak-ng", "-v", "en-gb", "-s", rate, text],
            capture_output=True
        )
    else:
        # Existing macOS code
        ...
```

**2. System Mute/Unmute (jarvis.py listener)**

The `_mute_system` and `_unmute_system` functions use `osascript` (macOS AppleScript).
On Pi, use `amixer`:

```python
def _mute_system():
    if platform.system() == "Linux":
        subprocess.run(["amixer", "-q", "set", "Headphone", "mute"],
                      capture_output=True, timeout=2)

def _unmute_system():
    if platform.system() == "Linux":
        subprocess.run(["amixer", "-q", "set", "Headphone", "unmute"],
                      capture_output=True, timeout=2)
```

**3. UI (jarvis.py main function)**

The `main()` function creates a `QApplication` and `JarvisWidget`. On Pi headless,
skip the UI:

```python
def main():
    if config.get("headless"):
        # Headless mode: no Qt, just run listener in main thread
        speech = SpeechEngine()
        # ... run listener loop directly
    else:
        # Existing Qt-based UI code
        app = QApplication(sys.argv)
        ...
```

**4. Voice listing (ui.py)**

The `list_voices` method calls `say -v ?` which is macOS-only. On Pi:

```python
@staticmethod
def list_voices():
    if platform.system() == "Linux":
        result = subprocess.run(["espeak-ng", "--voices=en"],
                              capture_output=True, text=True)
        # Parse espeak voice list
        ...
```

---

## 11. Auto-Start Jarvis on Boot (systemd)

### Install the Service

```bash
sudo cp /home/pi/Jarvis/pi_setup/jarvis.service /etc/systemd/system/jarvis.service
sudo systemctl daemon-reload
sudo systemctl enable jarvis
```

### Start Jarvis

```bash
sudo systemctl start jarvis
```

### Verify

```bash
# Check status
sudo systemctl status jarvis

# Watch logs in real time
journalctl -u jarvis -f

# Check if Jarvis greeted on startup
journalctl -u jarvis --no-pager | tail -20
```

### Service Details

The `jarvis.service` file:
- **Starts after** network and Ollama are ready
- **Restarts automatically** if Jarvis crashes (5-second delay)
- **Runs as the `pi` user** (not root)
- **Sets headless environment** (`QT_QPA_PLATFORM=offscreen`, no `DISPLAY`)
- **Limits resources** to 4GB RAM and 80% CPU to leave room for Ollama
- **Logs to journald** (view with `journalctl -u jarvis`)

### Manual Run (for debugging)

```bash
cd /home/pi/Jarvis
source venv/bin/activate
QT_QPA_PLATFORM=offscreen PYTHONUNBUFFERED=1 python3 jarvis.py
```

---

## 12. Optimization Tips

### Memory Management

The Pi 5 8GB must run Ollama (~4.5GB), Whisper (~150MB), and Python (~200MB)
simultaneously. Keep total usage under 7GB to avoid swap thrashing.

```bash
# Monitor memory in real time
watch -n 2 free -h

# Check what's using memory
ps aux --sort=-%mem | head -10
```

**Increase swap (already done by install.sh):**

```bash
# /etc/dphys-swapfile should have:
CONF_SWAPSIZE=2048
```

### GPU Memory

Since there is no display, minimize GPU allocation:

```bash
# In /boot/firmware/config.txt:
gpu_mem=16
```

### Reduce Whisper Overhead

- Use `tiny.en` (not `base.en`) for Pi -- 3x faster, good enough for commands
- Rely on Google STT for wake word detection (already the default pipeline)
- Whisper is the fallback when Google STT fails

### Ollama Optimization

```bash
# Limit Ollama context window to save RAM
# In the Ollama modelfile or via API parameter:
# "num_ctx": 2048  (default is 4096)

# Keep the model loaded (avoid reload latency)
# Ollama keeps models loaded for 5 minutes by default
# Increase with:
sudo systemctl edit ollama
# Add:
# [Service]
# Environment="OLLAMA_KEEP_ALIVE=30m"
```

### CPU Governor

Set the CPU to performance mode for consistent inference speed:

```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Make it persistent:
echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils
sudo apt-get install -y cpufrequtils
sudo systemctl restart cpufrequtils
```

### Disable Unnecessary Services

The install script already does this, but verify:

```bash
# These waste resources on a headless voice assistant:
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
sudo systemctl disable triggerhappy
```

### Network Optimization

Google STT requires internet. For reliability:

- Use Ethernet instead of WiFi when possible
- Set a static IP to avoid DHCP delays on boot
- If WiFi only, ensure the Pi has a strong signal

```bash
# Test network latency to Google
ping -c 5 www.google.com
```

### Temperature Monitoring

Sustained inference generates heat. Monitor and ensure the active cooler works:

```bash
# Check CPU temperature
vcgencmd measure_temp

# Continuous monitoring
watch -n 5 vcgencmd measure_temp

# Should stay under 70C with active cooling
# Throttling starts at 80C
```

---

## 13. Troubleshooting

### No sound from speaker

```bash
# Check ALSA default output
aplay -l
speaker-test -c 2 -t wav -l 1

# Check volume not muted
amixer -c 0 contents
amixer -c 0 set Headphone unmute
amixer -c 0 set Headphone 90%
```

### ReSpeaker not detected

```bash
# Check kernel module loaded
lsmod | grep snd_soc_wm8960

# If not loaded, the driver install may have failed
# Re-run the driver install:
cd /home/pi/seeed-voicecard
sudo ./install.sh
sudo reboot

# Check dmesg for errors
dmesg | grep -i "wm8960\|seeed\|voicecard\|i2c"
```

### Microphone not picking up audio

```bash
# Test direct recording with explicit device
arecord -D plughw:1,0 -f S16_LE -r 16000 -d 5 /tmp/test.wav
aplay /tmp/test.wav

# Check capture levels
amixer -c 1 contents
# Increase capture volume if needed
amixer -c 1 set Capture 100%
```

### Ollama out of memory

```bash
# Check memory
free -h

# If Ollama is killed by OOM, try a smaller model:
ollama pull mistral:7b-instruct-v0.3-q3_K_S  # Smaller quantization
# Or:
ollama pull phi3:mini-4k-instruct-q4_K_M      # Smaller model entirely

# Update config.json with the new model name
```

### Jarvis service fails to start

```bash
# Check detailed error
journalctl -u jarvis -e --no-pager

# Common issues:
# 1. Python venv not found -> check path in jarvis.service
# 2. Permission denied -> check User= in service file matches your username
# 3. Import error -> activate venv and run manually to see the full traceback
cd /home/pi/Jarvis
source venv/bin/activate
QT_QPA_PLATFORM=offscreen python3 jarvis.py
```

### PyQt6 import error on Pi

PyQt6 wheels are not available for ARM64. If the code tries to import PyQt6:

- The `config_pi.json` sets `"headless": true` -- your code should check this
  and skip all Qt imports
- As a fallback, the systemd service sets `QT_QPA_PLATFORM=offscreen`
- Long-term fix: refactor `jarvis.py` to conditionally import Qt only when
  headless mode is off

### espeak-ng sounds robotic

espeak-ng is functional but not natural-sounding. For better voice quality:

```bash
# Option 1: Install Piper TTS (neural, runs on Pi)
pip install piper-tts
# Download a voice model:
# https://github.com/rhasspy/piper/releases
# Use the en_US-lessac-medium model for good quality

# Option 2: Use festival
sudo apt-get install -y festival
echo "Hello world" | festival --tts
```

### High CPU usage

```bash
# Check what's consuming CPU
top -o %CPU

# Whisper inference is CPU-intensive -- tiny.en helps
# Reduce the phrase_time_limit in config.json for shorter recordings
# Increase pause_threshold so Jarvis waits longer before processing
```

---

## 14. Quick Start (One-Shot Install)

If you want to skip the manual steps, the `install.sh` script automates everything:

```bash
# 1. SSH into your Pi (Raspberry Pi OS 64-bit Lite already flashed)
ssh pi@jarvis.local

# 2. Get the Jarvis code onto the Pi (from your Mac):
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='.git' \
    --exclude='.DS_Store' \
    /Users/ankmishr4/Jarvis/ pi@jarvis.local:/home/pi/Jarvis/

# 3. On the Pi, run the installer:
cd /home/pi/Jarvis/pi_setup
chmod +x install.sh
./install.sh

# 4. Reboot to activate drivers and start Jarvis:
sudo reboot

# 5. After reboot, check Jarvis:
sudo systemctl status jarvis
journalctl -u jarvis -f
```

The installer handles: system packages, ReSpeaker drivers, ALSA config,
Ollama + model download, Python venv + all pip packages, systemd service,
swap/GPU/performance tuning.

---

## Architecture Notes

### How Jarvis Works on Pi vs macOS

| Component | macOS | Raspberry Pi |
|-----------|-------|-------------|
| TTS | `say` command + `afplay` | `espeak-ng` (or Piper TTS) |
| Audio effects | `sox` + `afplay` | `sox` + `aplay` |
| Microphone | Built-in or USB | ReSpeaker HAT via ALSA |
| Speaker | Built-in | 3.5mm jack or USB speaker |
| LLM | Ollama / Groq / Gemini / Claude | Ollama only (offline) |
| STT | Whisper base.en + Google | Whisper tiny.en + Google |
| UI | PyQt6 floating widget | None (headless) |
| Auto-start | launchd (LaunchAgent) | systemd service |
| System mute | AppleScript `osascript` | `amixer` |
| Process type | Background accessory app | systemd managed daemon |

### File Layout on Pi

```
/home/pi/Jarvis/
    jarvis.py           # Main entry point
    config.json         # Pi-optimized config (from config_pi.json)
    config.py           # Config loader
    brain.py            # LLM orchestrator shim
    commands.py         # Command processor
    memory.py           # Conversation memory
    tools.py            # Tool registry
    ui.py               # UI (unused in headless mode)
    requirements.txt    # Python dependencies
    venv/               # Python virtual environment
    data/               # Persistent data
    logs/               # Log files
    llm/                # LLM module
    orchestrator/       # Orchestrator module
    planner/            # Planner module
    tools_pkg/          # Tool implementations

/etc/asound.conf        # ALSA audio routing
/etc/systemd/system/jarvis.service  # Auto-start service
```
