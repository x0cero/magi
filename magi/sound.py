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


# The cue set.
#
# Retuned to sit closer to a 1990s operations console than to a generic app
# chime. Three properties do most of that work: the pips are very short (30 to
# 60ms), they are high and nearly pure, and the important ones are doubled or
# tripled rather than held. A held tone reads as a notification; a burst of
# short pips reads as a machine reporting.
#
# Frequencies stay on one spine so consecutive cues in a single deliberation do
# not clash with each other.
def _pip(freq: float, seconds: float = 0.032, volume: float = 0.20,
         kind: str = "sine") -> list[float]:
    """One short blip. The unit the console speaks in."""
    return _tone(freq, seconds, kind, volume)


def _burst(freqs: list[float], gap: float = 0.028, seconds: float = 0.032,
           volume: float = 0.20) -> list[float]:
    """Several pips in quick succession, which is what makes it read as data
    rather than as a chime."""
    out: list[float] = []
    for i, f in enumerate(freqs):
        if i:
            out += _silence(gap)
        out += _pip(f, seconds, volume)
    return out


def _build() -> dict[str, list[float]]:
    return {
        # Boot: a low sweep coming up under a three-pip confirmation.
        "boot": _mix(
            _tone(120, 0.62, "saw", 0.13, sweep_to=520),
            _silence(0.30) + _burst([1568, 1568, 2093], gap=0.045, seconds=0.045, volume=0.17),
        ),
        # A unit reports in. Doubled, because a single blip reads as a click and
        # a doubled one reads as an acknowledgement.
        "report": _burst([1760, 2093], gap=0.030, seconds=0.030, volume=0.15),
        # Sent back to find its own argument: the same shape, pitched down, so
        # it is recognisably the same event going the other way.
        "revote": _burst([988, 784], gap=0.030, seconds=0.034, volume=0.14),
        # Unanimous. The only cue that climbs and lands.
        "consensus": _burst([1046, 1319, 1568], gap=0.038, seconds=0.042, volume=0.17)
                     + _silence(0.02)
                     + _mix(_tone(1568, 0.30, "sine", 0.16),
                            _tone(2093, 0.30, "sine", 0.08)),
        # Two of three. Lands, but flat: nothing climbs, because somebody lost.
        "majority": _burst([1319, 1319], gap=0.045, seconds=0.045, volume=0.17)
                    + _silence(0.02)
                    + _tone(1319, 0.24, "sine", 0.15),
        # They split. Deliberately unresolved: it steps down and stops.
        "tiebreak": _burst([1175, 988], gap=0.055, seconds=0.055, volume=0.16)
                    + _silence(0.03)
                    + _tone(880, 0.26, "square", 0.11),
        # Something failed. Harsh and obviously wrong.
        "error": _mix(_tone(220, 0.34, "saw", 0.20, sweep_to=98),
                      _tone(233, 0.34, "saw", 0.12, sweep_to=104)),
        # Pattern alert, for the red states. The one cue allowed to nag.
        "alert": (_burst([1976, 1976], gap=0.035, seconds=0.048, volume=0.20)
                  + _silence(0.075)) * 3,
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


# Audio you supply yourself wins over the generated tone. Its own directory,
# because `SOUND_DIR` holds files this module writes and may rewrite, and a
# user's file must never be sitting where something else expects to own the
# name. Nothing is shipped or downloaded here: the show's audio is Khara's, so
# supplying it is the user's own business on their own machine.
CUSTOM_DIR = SOUND_DIR / "custom"
CUSTOM_EXTENSIONS = (".wav", ".aiff", ".aif", ".m4a", ".mp3", ".caf")


def _resolve(cue: str) -> Path | None:
    for extension in CUSTOM_EXTENSIONS:
        candidate = CUSTOM_DIR / f"{cue}{extension}"
        if candidate.exists():
            return candidate
    generated = SOUND_DIR / f"{cue}.wav"
    return generated if generated.exists() else None


def play(cue: str) -> None:
    """Fire a cue and return immediately. Never raises, never waits."""
    global _PLAYER
    if not enabled():
        return
    if _PLAYER is False:
        _PLAYER = _player() if ensure_sounds() else None
    if not _PLAYER:
        return
    path = _resolve(cue)
    if path is None:
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
