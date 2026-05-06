#!/usr/bin/env python3
"""
J.A.R.V.I.S. Debug Recorder
Records a 30-second mic session and transcribes every chunk with Whisper,
showing exactly what the recognizer hears.

Run while Jarvis is OFF (mic can't be shared):
    pkill -f jarvis.py
    python debug_recorder.py
"""
import sys, os, time, wave, tempfile
import speech_recognition as sr
import whisper
import config

DURATION = 30  # seconds to listen

print("=" * 60)
print("  J.A.R.V.I.S. DEBUG RECORDER")
print(f"  Listening for {DURATION} seconds — speak normally.")
print("  Each phrase will be saved + transcribed.")
print("=" * 60)

r = sr.Recognizer()
r.energy_threshold = 300
r.dynamic_energy_threshold = True
r.dynamic_energy_ratio = 1.4
r.pause_threshold = 0.8
r.phrase_threshold = 0.2
r.non_speaking_duration = 0.5

print("\n[Loading Whisper model...]", flush=True)
model_size = config.get("whisper_model") or "base"
model = whisper.load_model(model_size)
print(f"[Whisper '{model_size}' ready]\n", flush=True)

out_dir = "/tmp/jarvis_debug_audio"
os.makedirs(out_dir, exist_ok=True)

print("[Calibrating mic (2s) — stay silent]", flush=True)
with sr.Microphone() as source:
    r.adjust_for_ambient_noise(source, duration=2.0)
    print(f"[Ambient energy_threshold = {r.energy_threshold:.0f}]", flush=True)
    print(f"\n>>> SPEAK NOW — you have {DURATION} seconds <<<\n", flush=True)

    start = time.time()
    chunk_n = 0
    while time.time() - start < DURATION:
        try:
            remaining = DURATION - (time.time() - start)
            print(f"[{remaining:>4.1f}s left — waiting for speech...]", flush=True)
            audio = r.listen(source, timeout=remaining, phrase_time_limit=10)
            chunk_n += 1
            path = f"{out_dir}/chunk_{chunk_n:02d}.wav"
            with open(path, "wb") as f:
                f.write(audio.get_wav_data(convert_rate=16000, convert_width=2))

            # Transcribe with Whisper
            t = time.time()
            result = model.transcribe(
                path, language="en", fp16=False,
                no_speech_threshold=0.6, condition_on_previous_text=False,
            )
            elapsed = time.time() - t
            text = result["text"].strip()

            # Also get avg segment probabilities for confidence
            segs = result.get("segments", [])
            if segs:
                avg_logprob = sum(s.get("avg_logprob", 0) for s in segs) / len(segs)
                no_speech = sum(s.get("no_speech_prob", 0) for s in segs) / len(segs)
            else:
                avg_logprob = 0
                no_speech = 1.0

            size_kb = os.path.getsize(path) / 1024
            print(f"  #{chunk_n:02d} [{size_kb:.1f}KB, {elapsed:.1f}s] "
                  f"no_speech_prob={no_speech:.2f} confidence={avg_logprob:.2f}")
            print(f"        Heard: '{text}'")
            print(f"        Saved: {path}\n", flush=True)

        except sr.WaitTimeoutError:
            print("[Timeout — no speech detected in remaining time]", flush=True)
            break
        except Exception as e:
            print(f"[ERROR: {e}]", flush=True)
            break

print("=" * 60)
print(f"  SESSION DONE — {chunk_n} audio chunks captured")
print(f"  Audio saved in: {out_dir}")
print(f"  Review a chunk: afplay {out_dir}/chunk_01.wav")
print("=" * 60)
