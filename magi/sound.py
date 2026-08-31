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
           volume: float = 0.20, kind: str = "sine") -> list[float]:
    """Several pips in quick succession, which is what makes it read as data
    rather than as a chime."""
    out: list[float] = []
    for i, f in enumerate(freqs):
        if i:
            out += _silence(gap)
        out += _pip(f, seconds, volume, kind)
    return out


def _build() -> dict[str, list[float]]:
    """The cue set, built on the gated character.

    Chosen by ear over three alternatives. The console does not beep, it
    buzzes: a held tone chopped roughly thirty times a second reads as a
    machine working, where a clean pip reads as an app notification. Pitch and
    length carry the meaning; the chopping is constant across the set so they
    are recognisably one machine.

    Kept short deliberately. The report cue fires three times a round, and
    anything with a tail becomes unbearable by the second question.
    """
    return {
        # The console coming up: a gated tone rising under a settling buzz.
        "boot": _tremolo(196, 0.42, rate=24, volume=0.15)
                + _silence(0.03)
                + _tremolo(392, 0.30, rate=30, volume=0.15),

        # One unit answering. Short, mid, unremarkable on purpose.
        "report": _tremolo(440, 0.13, rate=28, volume=0.15),

        # Sent back to find its own argument: same event, pitched under it.
        "revote": _tremolo(330, 0.15, rate=26, volume=0.14),

        # Unanimous. The only cue that climbs, and the only one allowed to ring
        # out at the end.
        "consensus": _tremolo(523, 0.20, rate=30, volume=0.15)
                     + _tremolo(659, 0.20, rate=30, volume=0.15)
                     + _tone(784, 0.34, "square", 0.12),

        # Two of three. Lands flat: nothing climbs, because somebody lost.
        "majority": _tremolo(440, 0.22, rate=28, volume=0.15)
                    + _tone(440, 0.26, "square", 0.12),

        # They split. Steps down and stops without resolving.
        "tiebreak": _tremolo(415, 0.20, rate=26, volume=0.15)
                    + _tremolo(311, 0.24, rate=22, volume=0.14),

        # Something failed. Low, slow, obviously wrong.
        "error": _tremolo(147, 0.40, rate=16, volume=0.19, kind="saw"),

        # Pattern alert, the one cue allowed to nag.
        "alert": (_tremolo(659, 0.16, rate=34, volume=0.19) + _silence(0.09)) * 3,
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


def play_path(path: Path) -> None:
    """Play one specific file. Used by the character studies, which write a
    scratch file rather than polluting the cue set."""
    global _PLAYER
    if not enabled():
        return
    if _PLAYER is False:
        _PLAYER = _player()
    if not _PLAYER or not path.exists():
        return
    try:
        subprocess.Popen([*_PLAYER, str(path)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        _PLAYER = None


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


# ---------------------------------------------------------------------------
# Character studies.
#
# The cue set above is one guess at what the console sounds like, and guessing
# repeatedly is a bad way to converge. These are four different characters for
# the same event, so the choice can be made by ear instead:
#
#   1  bright   high, pure, doubled          (what is currently shipped)
#   2  relay    low, harsh, square           closer to a mechanical console
#   3  detune   two tones a few Hz apart     gritty, beating against itself
#   4  chatter  a fast run of tiny pips      telemetry rather than a chime
#
# `magi sounds --variants` plays all four of the cue heard most often.
def variants(cue: str = "report") -> dict[str, list[float]]:
    if cue == "report":
        return {
            "1 bright": _burst([1760, 2093], gap=0.030, seconds=0.030, volume=0.15),
            "2 relay": _burst([440, 392], gap=0.026, seconds=0.030, volume=0.16, kind="square"),
            "3 detune": _mix(_tone(523, 0.075, "square", 0.13),
                             _tone(529, 0.075, "square", 0.13)),
            "4 chatter": _burst([880, 784, 880, 988, 784], gap=0.016,
                                seconds=0.018, volume=0.13, kind="square"),
        }
    if cue == "verdict":
        return {
            "1 bright": _burst([1046, 1319, 1568], gap=0.038, seconds=0.042, volume=0.17),
            "2 relay": _burst([294, 294, 392], gap=0.055, seconds=0.075, volume=0.18, kind="square")
                       + _silence(0.02) + _tone(392, 0.34, "square", 0.13),
            "3 detune": _mix(_tone(330, 0.55, "square", 0.14),
                             _tone(334, 0.55, "square", 0.14),
                             _tone(660, 0.55, "sine", 0.06)),
            "4 chatter": _burst([523] * 7, gap=0.020, seconds=0.020, volume=0.13, kind="square")
                         + _silence(0.03) + _tone(392, 0.40, "saw", 0.15),
        }
    return {}


def _tremolo(freq: float, seconds: float, rate: float, volume: float = 0.16,
             kind: str = "square", depth: float = 1.0) -> list[float]:
    """A tone chopped rapidly by an amplitude gate.

    The characteristic console sound is not a clean beep: it stutters. Gating
    a held tone at 20-40Hz is what turns a tone into something that reads as a
    machine working rather than a machine notifying.
    """
    base = _tone(freq, seconds, kind, volume)
    out: list[float] = []
    for i, sample in enumerate(base):
        gate = 1.0 if (i * rate / SAMPLE_RATE) % 1.0 < 0.5 else (1.0 - depth)
        out.append(sample * gate)
    return out


def _warble(a: float, b: float, seconds: float, rate: float,
            volume: float = 0.16, kind: str = "square") -> list[float]:
    """Two pitches alternating fast enough to read as one unstable sound."""
    n = int(SAMPLE_RATE * seconds)
    out: list[float] = []
    phase = 0.0
    for i in range(n):
        freq = a if (i * rate / SAMPLE_RATE) % 1.0 < 0.5 else b
        phase += freq / SAMPLE_RATE
        sample = _square(phase, 0.35) if kind == "square" else math.sin(2.0 * math.pi * phase)
        out.append(sample * volume * _envelope(i, n))
    return out


def _ratchet(freq: float, count: int, volume: float = 0.15,
             kind: str = "square") -> list[float]:
    """A run of pips that accelerates. Reads as a process spinning up."""
    out: list[float] = []
    gap = 0.055
    for _ in range(count):
        out += _pip(freq, 0.020, volume, kind)
        out += _silence(max(0.008, gap))
        gap *= 0.78
    return out


# Second round, aimed at the stuttering quality rather than the pitch. The
# first round varied how high and how clean the beep was, which was the wrong
# axis: the console does not beep, it chatters.
def stutter_variants() -> dict[str, list[float]]:
    return {
        "1 gated": _tremolo(440, 0.36, rate=28),
        "2 warble": _warble(523, 392, 0.34, rate=22),
        "3 ratchet": _ratchet(660, 9),
        "4 sweep-stutter": _tremolo(880, 0.30, rate=34)
                           + _silence(0.02)
                           + _tone(880, 0.22, "square", 0.13, sweep_to=330),
    }
