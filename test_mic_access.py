#!/usr/bin/env python3
"""Quick check: does this Python process actually get audio from the mic?"""
import speech_recognition as sr
import numpy as np
r = sr.Recognizer()
with sr.Microphone() as source:
    audio = r.record(source, duration=2.0)
samples = np.frombuffer(audio.frame_data, dtype=np.int16)
rms = float(np.sqrt(np.mean(samples.astype(np.float64)**2)))
peak = int(np.max(np.abs(samples)))
n_nonzero = int(np.count_nonzero(samples))
total = len(samples)
print(f"Samples: {total}")
print(f"Non-zero: {n_nonzero} ({100*n_nonzero/total:.1f}%)")
print(f"Peak: {peak}")
print(f"RMS: {rms:.1f}")
if peak == 0 or n_nonzero == 0:
    print("❌ MIC IS SILENT — macOS is returning empty audio. Permission denied.")
elif rms < 5:
    print("⚠  Mic is nearly silent — may be muted or permission restricted.")
else:
    print("✓ Mic is capturing real audio.")
