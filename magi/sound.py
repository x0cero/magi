"""Console tones for the MAGI display.

Every sound here is synthesised from arithmetic at first use and cached in
`~/.config/magi/sounds/`. Nothing is shipped, downloaded, or sampled: audio
from the show is somebody else's copyright and this is a public repo, so the
cues are built to evoke a 1995 operations console rather than to reproduce one.

Playback is fire-and-forget. A cue that cannot play, because there is no audio
tool on the box or the file could not be written, is silently skipped: a
decision council that blocks on a beep is worse than a silent one.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

SAMPLE_RATE = 22050
SOUND_DIR = Path.home() / ".config" / "magi" / "sounds"

# One env var, checked at call time so it can be flipped inside a session.
def enabled() -> bool:
    raw = os.environ.get("MAGI_SOUND", "1").strip().lower()
    return raw not in ("0", "off", "false", "no", "")


def _envelope(i: int, total: int, attack: float = 0.01, release: float = 0.25) -> float:
    """Linear attack, exponential release. A raw sine that starts and stops at
    full amplitude clicks audibly on every cue."""
    t = i / total
    if t < attack:
        return t / attack
    if t > 1.0 - release:
        return max(0.0, (1.0 - t) / release) ** 1.5
    return 1.0


def _square(phase: float, duty: float = 0.5) -> float:
    return 1.0 if (phase % 1.0) < duty else -1.0


def _tone(freq: float, seconds: float, kind: str = "sine", volume: float = 0.35,
          sweep_to: float | None = None) -> list[float]:
    n = int(SAMPLE_RATE * seconds)
    out: list[float] = []
    phase = 0.0
    for i in range(n):
        f = freq if sweep_to is None else freq + (sweep_to - freq) * (i / n)
        phase += f / SAMPLE_RATE
        if kind == "square":
            sample = _square(phase, 0.35)
        elif kind == "saw":
            sample = 2.0 * (phase % 1.0) - 1.0
        else:
            sample = math.sin(2.0 * math.pi * phase)
        out.append(sample * volume * _envelope(i, n))
    return out


def _silence(seconds: float) -> list[float]:
    return [0.0] * int(SAMPLE_RATE * seconds)


def _mix(*layers: list[float]) -> list[float]:
    """Overlay equal-start layers, clipped. Used for the two-tone chords."""
    length = max(len(x) for x in layers)
    out = [0.0] * length
    for layer in layers:
        for i, s in enumerate(layer):
            out[i] += s
    return [max(-1.0, min(1.0, s)) for s in out]


def _write(path: Path, samples: list[float]) -> None:
    frames = b"".join(struct.pack("<h", int(s * 32767)) for s in samples)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(frames)


# The cue set. Frequencies picked to sit together: a G-minor-ish spine, so
# consecutive cues in one deliberation do not clash.
def _build() -> dict[str, list[float]]:
    return {
        # Boot: a rising sweep with a confirming blip, the console coming up.
        "boot": _tone(180, 0.55, "saw", 0.22, sweep_to=760)
                + _silence(0.05)
                + _mix(_tone(784, 0.18, "sine", 0.28), _tone(1176, 0.18, "sine", 0.14)),
        # A member reports in. Short, dry, repeated three times a round.
        "report": _tone(1046, 0.055, "square", 0.16),
        # Sent back to find its own argument: the same blip, pitched down.
        "revote": _tone(660, 0.07, "square", 0.14),
        # Unanimous. The only cue that resolves upward on a major interval.
        "consensus": _mix(_tone(523, 0.42, "sine", 0.26, sweep_to=659),
                          _tone(784, 0.42, "sine", 0.16, sweep_to=988)),
        # 2-1. Decided, but somebody lost: flat, no resolution.
        "majority": _mix(_tone(523, 0.34, "sine", 0.24),
                         _tone(698, 0.34, "sine", 0.14)),
        # Decided on conviction or broken by the desire lens. Unsettled.
        "tiebreak": _tone(415, 0.30, "square", 0.16)
                    + _tone(392, 0.34, "square", 0.16),
        # Something failed. Descending, obviously wrong.
        "error": _tone(330, 0.30, "saw", 0.24, sweep_to=110),
        # Pattern alert, for the red-frame states.
        "alert": (_tone(880, 0.13, "square", 0.20) + _silence(0.06)) * 3,
    }


def ensure_sounds() -> bool:
    """Synthesise any missing cue. Returns False if the directory is unusable."""
    try:
        SOUND_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    built: dict[str, list[float]] | None = None
    for name in _build_names():
        path = SOUND_DIR / f"{name}.wav"
        if path.exists():
            continue
        if built is None:
            built = _build()
        try:
            _write(path, built[name])
        except OSError:
            return False
    return True


def _build_names() -> tuple[str, ...]:
    return ("boot", "report", "revote", "consensus", "majority", "tiebreak", "error", "alert")


def _player() -> list[str] | None:
    """First available non-blocking player. afplay ships with macOS."""
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay"]
    for cmd, args in (("paplay", []), ("aplay", ["-q"]), ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"])):
        if shutil.which(cmd):
            return [cmd, *args]
    return None


_PLAYER: list[str] | None | bool = False  # False = not yet probed


def play(cue: str) -> None:
    """Fire a cue and return immediately. Never raises, never waits."""
    global _PLAYER
    if not enabled():
        return
    if _PLAYER is False:
        _PLAYER = _player() if ensure_sounds() else None
    if not _PLAYER:
        return
    path = SOUND_DIR / f"{cue}.wav"
    if not path.exists():
        return
    try:
        subprocess.Popen(
            [*_PLAYER, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        _PLAYER = None


OUTCOME_CUE = {
    "consensus": "consensus",
    "picks": "consensus",
    "majority": "majority",
    "conviction": "tiebreak",
    "tiebreak": "tiebreak",
    "deadlock": "alert",
    "split": "alert",
    "incomplete": "error",
}


def play_outcome(outcome: str) -> None:
    play(OUTCOME_CUE.get(outcome, "majority"))
