"""Generate original, short, quiet UI sound effects for Peachy.

Uses standard Python wave and numpy to synthesize 44.1 kHz, 16-bit mono WAV files:
- open: soft two-note rising chime (~160 ms)
- capture: very soft shutter (~70 ms)
- answer: gentle single bell with a short tail (~300 ms)
- copy: tiny tick (~40 ms)
- error: soft two-note falling tone (~220 ms)

All sounds feature smooth fade-in and fade-out envelopes to prevent any pops/clicks.
Zero external audio files or copyrighted samples.
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import wave
import numpy as np

SAMPLE_RATE = 44100


def apply_envelope(signal: np.ndarray, fade_in_ms: float = 4.0, fade_out_ms: float = 10.0) -> np.ndarray:
    """Apply smooth cosine-based fade-in and fade-out ramps to avoid audio pops."""
    n_samples = len(signal)
    in_samples = int((fade_in_ms / 1000.0) * SAMPLE_RATE)
    out_samples = int((fade_out_ms / 1000.0) * SAMPLE_RATE)

    in_samples = min(in_samples, n_samples // 2)
    out_samples = min(out_samples, n_samples // 2)

    envelope = np.ones(n_samples, dtype=np.float32)

    if in_samples > 0:
        # Cosine fade in: 0.0 -> 1.0
        t = np.linspace(0.0, np.pi / 2.0, in_samples, dtype=np.float32)
        envelope[:in_samples] = np.sin(t)

    if out_samples > 0:
        # Cosine fade out: 1.0 -> 0.0
        t = np.linspace(np.pi / 2.0, np.pi, out_samples, dtype=np.float32)
        envelope[-out_samples:] = np.sin(t)

    return signal * envelope


def save_wav(filepath: Path, samples: np.ndarray) -> None:
    """Save 1D float array [-1.0, 1.0] as 16-bit mono 44.1 kHz WAV."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    int16_samples = (clipped * 32767.0).astype(np.int16)

    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)        # mono
        wf.setsampwidth(2)        # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(int16_samples.tobytes())


def make_open_chime() -> np.ndarray:
    """Soft two-note rising chime, about 160 ms."""
    dur = 0.160
    n = int(dur * SAMPLE_RATE)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
    sig = np.zeros(n, dtype=np.float32)

    half = n // 2
    # Note 1: 659.25 Hz (E5)
    t1 = t[:half]
    decay1 = np.exp(-t1 / 0.035)
    sig[:half] = (np.sin(2 * np.pi * 659.25 * t1) + 0.25 * np.sin(2 * np.pi * 1318.5 * t1)) * decay1

    # Note 2: 987.77 Hz (B5)
    t2 = t[half:] - t[half]
    decay2 = np.exp(-t2 / 0.045)
    sig[half:] = (np.sin(2 * np.pi * 987.77 * t2) + 0.20 * np.sin(2 * np.pi * 1975.54 * t2)) * decay2

    sig = apply_envelope(sig, fade_in_ms=4.0, fade_out_ms=15.0)
    return sig * 0.22


def make_capture_shutter() -> np.ndarray:
    """Very soft shutter (short filtered noise burst), about 70 ms."""
    dur = 0.070
    n = int(dur * SAMPLE_RATE)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)

    # Shaped noise with gentle resonance
    rng = np.random.default_rng(42)
    noise = rng.uniform(-1.0, 1.0, n).astype(np.float32)

    # Simple moving average lowpass filter to soften noise harshness
    kernel_size = 9
    kernel = np.ones(kernel_size, dtype=np.float32) / kernel_size
    smoothed = np.convolve(noise, kernel, mode="same")

    # Add gentle mechanical impulse click at 900 Hz
    click = np.sin(2 * np.pi * 880.0 * t) * np.exp(-t / 0.010)

    # Shutter envelope: fast attack, quick decay
    env = np.exp(-t / 0.018)
    sig = (0.7 * smoothed * env) + (0.3 * click)

    sig = apply_envelope(sig, fade_in_ms=2.0, fade_out_ms=10.0)
    return sig * 0.16


def make_answer_bell() -> np.ndarray:
    """Gentle single bell with a short tail, about 300 ms."""
    dur = 0.300
    n = int(dur * SAMPLE_RATE)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)

    # Bell harmonic spectrum: 784 Hz (G5) fundamental + soft overtones
    f0 = 783.99
    h1 = np.sin(2 * np.pi * f0 * t)
    h2 = 0.28 * np.sin(2 * np.pi * (f0 * 2.0) * t)
    h3 = 0.08 * np.sin(2 * np.pi * (f0 * 3.0) * t)
    h4 = 0.04 * np.sin(2 * np.pi * (f0 * 4.2) * t)

    decay = np.exp(-t / 0.080)
    sig = (h1 + h2 + h3 + h4) * decay

    sig = apply_envelope(sig, fade_in_ms=3.0, fade_out_ms=25.0)
    return sig * 0.24


def make_copy_tick() -> np.ndarray:
    """Tiny tick, about 40 ms."""
    dur = 0.040
    n = int(dur * SAMPLE_RATE)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)

    # Crisp high tap at 1760 Hz (A6) with rapid exponential drop
    f0 = 1760.0
    sig = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.007)

    sig = apply_envelope(sig, fade_in_ms=1.5, fade_out_ms=8.0)
    return sig * 0.14


def make_error_tone() -> np.ndarray:
    """Soft two-note falling tone, about 220 ms."""
    dur = 0.220
    n = int(dur * SAMPLE_RATE)
    t = np.linspace(0, dur, n, endpoint=False, dtype=np.float32)
    sig = np.zeros(n, dtype=np.float32)

    half = n // 2
    # Note 1: 440 Hz (A4)
    t1 = t[:half]
    decay1 = np.exp(-t1 / 0.050)
    sig[:half] = (np.sin(2 * np.pi * 440.0 * t1) + 0.15 * np.sin(2 * np.pi * 880.0 * t1)) * decay1

    # Note 2: 329.63 Hz (E4) falling
    t2 = t[half:] - t[half]
    decay2 = np.exp(-t2 / 0.055)
    sig[half:] = (np.sin(2 * np.pi * 329.63 * t2) + 0.15 * np.sin(2 * np.pi * 659.25 * t2)) * decay2

    sig = apply_envelope(sig, fade_in_ms=4.0, fade_out_ms=18.0)
    return sig * 0.20


def generate_all_sounds(output_dir: Path | str | None = None) -> dict[str, Path]:
    """Generate all UI sound files and save them to output_dir."""
    if output_dir is None:
        target_dir = Path(__file__).resolve().parent.parent / "resources" / "sounds"
    else:
        target_dir = Path(output_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    sounds = {
        "open.wav": make_open_chime(),
        "capture.wav": make_capture_shutter(),
        "answer.wav": make_answer_bell(),
        "copy.wav": make_copy_tick(),
        "error.wav": make_error_tone(),
    }

    generated: dict[str, Path] = {}
    for filename, data in sounds.items():
        dest = target_dir / filename
        save_wav(dest, data)
        generated[filename] = dest
        duration_ms = (len(data) / SAMPLE_RATE) * 1000.0
        print(f"Generated {filename}: {len(data)} samples ({duration_ms:.1f} ms) -> {dest}")

    return generated


if __name__ == "__main__":
    generate_all_sounds()
