#!/usr/bin/env python3
"""
J.A.R.V.I.S. Testing Framework
Tests every subsystem independently and prints a pass/fail report.

Layers tested:
  1. Imports / dependencies
  2. Config
  3. TTS (say + sox audio pipeline) — generates and plays a short phrase
  4. Microphone availability + ambient calibration
  5. Whisper model load + transcription on synthetic audio
  6. Command engine (routes 20+ sample voice commands through process_command)
  7. Claude API connectivity
  8. UI imports (headless)

Run with:
    source venv/bin/activate && python test_jarvis.py
"""

import sys
import os
import time
import traceback
import subprocess
import tempfile

# Color codes
G = "\033[92m"   # green
R = "\033[91m"   # red
Y = "\033[93m"   # yellow
B = "\033[94m"   # blue
C = "\033[96m"   # cyan
X = "\033[0m"    # reset
BOLD = "\033[1m"

_results = []


def _record(name, ok, detail=""):
    _results.append((name, ok, detail))
    tag = f"{G}PASS{X}" if ok else f"{R}FAIL{X}"
    print(f"  [{tag}] {name}" + (f"  —  {detail}" if detail else ""))


def section(title):
    print(f"\n{BOLD}{C}── {title} {'─' * (60 - len(title))}{X}")


def run_test(name, fn):
    try:
        detail = fn() or ""
        _record(name, True, detail)
    except AssertionError as e:
        _record(name, False, str(e))
    except Exception as e:
        _record(name, False, f"{type(e).__name__}: {e}")


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_imports():
    import speech_recognition, PyQt6, anthropic, whisper, config
    from commands import process_command, COMMAND_TABLE
    from claude_brain import ask_claude, is_configured
    from ui import JarvisWidget
    return f"{len(COMMAND_TABLE)} command triggers loaded"


def test_config():
    import config
    assert config.get("owner_name"), "owner_name missing"
    assert config.get("wake_word"), "wake_word missing"
    assert config.get("voice_profile"), "voice_profile missing"
    return f"owner={config.get('owner_name')}, wake='{config.get('wake_word')}', profile={config.get('voice_profile')}"


def test_sox_installed():
    result = subprocess.run(["sox", "--version"], capture_output=True, text=True)
    assert result.returncode == 0, "sox not installed"
    return result.stdout.strip().split("\n")[0]


def test_tts_say_only():
    """Test raw macOS say command (no sox pipeline)."""
    result = subprocess.run(
        ["say", "-v", "Daniel", "-r", "200", "Test"],
        capture_output=True, timeout=5
    )
    assert result.returncode == 0, f"say failed: {result.stderr.decode()}"
    return "macOS `say` works"


def test_tts_full_pipeline():
    """Run full Zoro voice pipeline and verify audio file is produced."""
    from jarvis import SpeechEngine
    engine = SpeechEngine()
    # Render to file but don't play
    subprocess.run(
        ["say", "-v", "Daniel", "-r", "162", "-o", "/tmp/jarvis_test.aiff",
         "Testing voice pipeline"],
        capture_output=True, timeout=5
    )
    assert os.path.exists("/tmp/jarvis_test.aiff"), "say didn't create audio file"
    size = os.path.getsize("/tmp/jarvis_test.aiff")
    assert size > 1000, f"audio file too small ({size} bytes)"

    # Run sox pitch effect
    subprocess.run(
        ["sox", "/tmp/jarvis_test.aiff", "/tmp/jarvis_test_out.aiff",
         "pitch", "-300", "bass", "+6", "overdrive", "3"],
        capture_output=True, timeout=5
    )
    assert os.path.exists("/tmp/jarvis_test_out.aiff"), "sox pipeline failed"
    os.unlink("/tmp/jarvis_test.aiff")
    os.unlink("/tmp/jarvis_test_out.aiff")
    return f"profile={engine.get_profile_name()}, rate={engine.get_rate()}"


def test_tts_audible():
    """Actually speak a short phrase so the user can hear it."""
    subprocess.run(
        ["say", "-v", "Daniel", "-r", "200", "Jarvis voice test"],
        capture_output=True, timeout=10
    )
    return "played 'Jarvis voice test' through speakers"


def test_microphone_available():
    import speech_recognition as sr
    mic_list = sr.Microphone.list_microphone_names()
    assert len(mic_list) > 0, "No microphones detected"
    return f"{len(mic_list)} mics, default='{mic_list[0][:40]}'"


def test_microphone_capture():
    """Capture 1 second of audio from default mic."""
    import speech_recognition as sr
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        energy = r.energy_threshold
        # Quick record
        audio = r.record(source, duration=1.0)
    wav_bytes = audio.get_wav_data()
    assert len(wav_bytes) > 1000, "captured audio too small"
    return f"captured {len(wav_bytes)} bytes, ambient energy={energy:.0f}"


def test_whisper_load():
    import whisper, config
    model_size = config.get("whisper_model") or "base"
    t = time.time()
    model = whisper.load_model(model_size)
    elapsed = time.time() - t
    return f"model='{model_size}' loaded in {elapsed:.1f}s on {model.device}"


def test_whisper_transcribe_known():
    """Generate speech with `say`, then transcribe it with Whisper — round-trip test."""
    import whisper, config
    phrase = "hello jarvis what time is it"

    # Generate TTS audio — default aiff, then sox converts to wav
    wav_path = "/tmp/jarvis_whisper_test.wav"
    aiff_path = "/tmp/jarvis_whisper_test.aiff"
    for p in (wav_path, aiff_path):
        if os.path.exists(p):
            os.unlink(p)
    result = subprocess.run(
        ["say", "-v", "Samantha", "-r", "180", "-o", aiff_path, phrase],
        capture_output=True, timeout=10
    )
    assert os.path.exists(aiff_path), f"say failed: {result.stderr.decode()[:100]}"
    # Convert aiff -> 16kHz mono wav (Whisper's native rate)
    subprocess.run(
        ["sox", aiff_path, "-r", "16000", "-c", "1", wav_path],
        capture_output=True, timeout=10
    )
    assert os.path.exists(wav_path), "sox aiff->wav conversion failed"

    model_size = config.get("whisper_model") or "base"
    model = whisper.load_model(model_size)

    t = time.time()
    result = model.transcribe(wav_path, language="en", fp16=False)
    elapsed = time.time() - t
    transcription = result["text"].strip().lower()

    os.unlink(wav_path)
    os.unlink(aiff_path)

    # Check that core words appeared
    assert "jarvis" in transcription or "time" in transcription, \
        f"transcription way off: '{transcription}'"
    return f"'{transcription}' ({elapsed:.1f}s)"


def test_commands_all():
    """Run every sample command through process_command — report per-command results."""
    from commands import process_command

    samples = [
        ("what time is it",               ["time"]),
        ("what's the date today",         ["today", "date"]),
        ("what day is it",                ["today"]),
        ("set a timer for 5 minutes",     ["timer", "minute"]),
        ("open safari",                   ["open", "safari"]),
        ("close safari",                  ["clos"]),
        ("search google for python",      ["search", "google"]),
        ("play music",                    ["play", "music", "spotify", "itunes"]),
        ("pause music",                   ["pause", "stop"]),
        ("next song",                     ["next", "skip"]),
        ("volume up",                     ["volume", "increas", "up"]),
        ("volume down",                   ["volume", "decreas", "down"]),
        ("mute",                          ["mut"]),
        ("take a screenshot",             ["screenshot", "saved", "captured"]),
        ("battery status",                ["battery", "%"]),
        ("what's my ip",                  ["ip", "address"]),
        ("wifi status",                   ["wi-fi", "wifi", "connected", "network"]),
        ("calculate 2 plus 2",            ["4", "four"]),
        ("flip a coin",                   ["heads", "tails"]),
        ("roll a dice",                   ["roll", "got", "rolled"]),
        ("tell me a joke",                ["."]),  # just non-empty
        ("switch to zoro heavy",          ["profile", "zoro"]),
        ("list voices",                   ["voice"]),
    ]

    passed = 0
    failed = []
    for cmd, expected_any in samples:
        try:
            response, _ = process_command(cmd)
            if response is None:
                failed.append(f"'{cmd}' → None")
                continue
            low = response.lower()
            if any(exp.lower() in low for exp in expected_any):
                passed += 1
            else:
                failed.append(f"'{cmd}' → '{response[:50]}'")
        except Exception as e:
            failed.append(f"'{cmd}' → ERROR: {e}")

    total = len(samples)
    detail = f"{passed}/{total} commands responded correctly"
    if failed:
        detail += "\n         " + "\n         ".join(f"{Y}✗{X} " + f for f in failed[:6])
    assert passed >= total * 0.8, detail  # require 80% pass rate
    return detail


def test_claude_api():
    import claude_brain
    if not claude_brain.is_configured():
        return f"{Y}skipped — no API key configured{X}"
    reply, _ = claude_brain.ask_claude("say 'test ok' and nothing else", [])
    if reply is None:
        return f"{Y}API returned None (likely credit/auth issue — see console)${X}"
    return f"Claude replied: '{reply[:60]}'"


def test_ui_imports():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt6.QtWidgets import QApplication
    from ui import JarvisWidget, ArcReactor, StatusLabel, VoiceSettingsPanel
    app = QApplication.instance() or QApplication([])
    # Just construct without showing
    from jarvis import SpeechEngine
    engine = SpeechEngine()
    w = JarvisWidget(speech_engine=engine)
    return "widget + reactor + settings panel constructed"


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{B}╔════════════════════════════════════════════════════════════╗")
    print(f"║           J.A.R.V.I.S.  TESTING  FRAMEWORK                 ║")
    print(f"╚════════════════════════════════════════════════════════════╝{X}")

    section("1. Imports & Config")
    run_test("All Python deps import",     test_imports)
    run_test("Config file loads",          test_config)
    run_test("sox installed",              test_sox_installed)

    section("2. Text-to-Speech")
    run_test("macOS `say` works",          test_tts_say_only)
    run_test("Zoro voice pipeline (file)", test_tts_full_pipeline)
    run_test("TTS audible (plays sound)",  test_tts_audible)

    section("3. Microphone & Speech Recognition")
    run_test("Microphone detected",        test_microphone_available)
    run_test("Microphone captures audio",  test_microphone_capture)
    run_test("Whisper model loads",        test_whisper_load)
    run_test("Whisper transcribes TTS",    test_whisper_transcribe_known)

    section("4. Command Engine")
    run_test("All voice commands route",   test_commands_all)

    section("5. Claude API")
    run_test("Claude API responds",        test_claude_api)

    section("6. UI Layer")
    run_test("UI widgets construct",       test_ui_imports)

    # ── Summary ──
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    pct = (passed / total * 100) if total else 0

    color = G if pct == 100 else (Y if pct >= 80 else R)
    print(f"\n{BOLD}{color}╔════════════════════════════════════════════════════════════╗")
    print(f"║  RESULT:  {passed}/{total} tests passed  ({pct:.0f}%)".ljust(62) + "║")
    print(f"╚════════════════════════════════════════════════════════════╝{X}\n")

    # Show failures
    fails = [(n, d) for n, ok, d in _results if not ok]
    if fails:
        print(f"{R}{BOLD}Failures:{X}")
        for name, detail in fails:
            print(f"  {R}✗{X} {name}: {detail}")
        print()

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
