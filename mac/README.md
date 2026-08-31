# MAGI.app

The console as a real Mac app: the three units in the triangle, glowing, with
the verdict taking the whole screen when the council lands.

## Build

```bash
./mac/build.sh
```

Needs `xcodegen` (`brew install xcodegen`). Builds Release and copies the app
to `/Applications`. Ad-hoc signed, which is fine for a locally built app and
not fine for one that moves between machines.

## How it talks to the council

The app contains **no council logic**. It spawns the Python engine and reads
newline-delimited JSON from it:

```bash
magi stream "should i deploy on friday"   # one event per line
magi roster                                # who is seated, for the idle display
```

That split is deliberate. The personas, the validators, the grounding rules and
the tie-breaking are 1,400 lines of Python that the eval harness measures. A
Swift reimplementation would be a second copy of all of it that no eval ever
scores, and the two would drift the first time a prompt changed.

The wire format lives in `magi/stream.py`, its tests in `tests/test_stream.py`,
and its Swift half in `mac/MAGI/Engine/Event.swift`. `PROTOCOL_VERSION` is
asserted on both sides; bumping it is a deliberate, matched change.

## Finding the engine

In order: a pinned `enginePath` default, `~/.local/bin/magi` (pipx), the repo's
own `.venv`, then Homebrew. So a dev checkout and a normal install both work
with nothing to configure.

## Settings

```bash
defaults write io.zeroarch.magi stampSeconds -float 5   # verdict hold, default 2.6
defaults write io.zeroarch.magi soundEnabled -bool false
defaults write io.zeroarch.magi enginePath "/path/to/magi"
```

## Sound

Synthesised in the app from arithmetic, not sampled from the show. A unit
reporting clicks, a unanimous council resolves upward, a tiebreak does not
resolve. Audio failing to start is silence, never an error: a decision tool
must not fall over on a beep.
