# Contributing to MAGI

Thanks for wanting to contribute. Here's how to get started.

## Setup

```bash
git clone https://github.com/x0cero/magi
cd magi
pip install -e ".[dev]"
```

Requires [Ollama](https://ollama.com) running locally for integration testing.

## Running tests

```bash
pytest tests/ -v
```

Tests cover validators, synthesis, config, journal, memory, security, and intake parsing. They don't hit Ollama (no network required).

## Linting

```bash
ruff check magi/ tests/
```

## Design rules

These are non-negotiable. Read them before opening a PR.

- **The council DECIDES.** Never add a "refuse to vote" / "needs more info" / "motion tabled" verdict. Even on vague input, personas pick a verdict.
- **Personas are decisive, not interrogators.** No clarifying questions, no "have you considered..." patterns.
- **CONDITIONAL must be costly.** Requires a concrete blocker tied to the user's specifics. Vague conditions are coerced to ACCEPT by validators.
- **Hold-your-line over convergence.** Debate rounds must not pressure consensus. Convergence for its own sake is failure.
- **Three is canon.** Don't add a 4th core member. Route through specialists.
- **No Eva cosplay in prompts.** The MAGI/Melchior/Balthasar/Casper names are branding. The lenses are the personas, not the anime characters.
- **Default models must run on 32GB+ machines.** Current defaults total ~25GB. Don't bump without checking the footprint.

## What to work on

Check the [issues](https://github.com/x0cero/magi/issues) for open items. Good first contributions:

- New specialist lenses (follow the pattern in `personas.py`)
- Intake classifier improvements (better edge case handling)
- Journal analytics extensions
- Documentation improvements
