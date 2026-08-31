# MAGI

[![CI](https://github.com/x0cero/magi/actions/workflows/ci.yml/badge.svg)](https://github.com/x0cero/magi/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A council that decides. Three models, three fixed lenses, one verdict you can argue with.

Named for the Nerv supercomputer in *Neon Genesis Evangelion*: three perspectives, one verdict. Built for indecisive people who want a council, not another chatbot.

MAGI is not a "which model gives the best answer" tool. There are plenty of those now. It is a decision instrument: the same three lenses every time, a verdict it will not take back, and a journal of what you actually did afterward.

```
    ███╗   ███╗ █████╗  ██████╗ ██╗
    ████╗ ████║██╔══██╗██╔════╝ ██║
    ██╔████╔██║███████║██║  ███╗██║
    ██║╚██╔╝██║██╔══██║██║   ██║██║
    ██║ ╚═╝ ██║██║  ██║╚██████╔╝██║
    ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝

    MELCHIOR  ·  BALTHASAR  ·  CASPER
    the council convenes — bring your question
```

## What it does

You bring a question. Three models, each running a distinct lens, debate it across multiple rounds and return a verdict:

- **MELCHIOR** (`qwen3:4b`) — data, logic, second-order effects. Owns the numbers, the runway, the mechanism. Watches for confirmation bias, sunk cost, planning fallacy.
- **BALTHASAR** (`dolphin3:8b`) — long-term wellbeing, relationships, what gets sacrificed quietly. Owns reversibility and who gets hurt. Never argues from money.
- **CASPER** (`hermes3:8b`) — desire, values, identity. Owns what you actually want under the framing. The one voice in the room willing to say go.

Each member must produce one **finding only its lens can produce** — a mechanism, a cost, a want — and each is told which arguments belong to the others so it cannot borrow them. A member is sent back to answer again if it restates somebody else's point, argues from a lens it does not own, or **asserts a fact your question never gave it**.

That last one is the failure that matters most. Asked "should i push a database migration to prod at 5pm on friday" with no other detail, an earlier build voted YES because one member decided you had "a 24-hour rollback window with pre-migration testing in staging". You never said that. Naming a missing fact is the job; assuming one is not.

Every member also reports **conviction**, 1 to 5. Conviction is what breaks a tie.

### It always lands on an answer

| result | what happened |
|---|---|
| `CONSENSUS — NO` | all three agreed |
| `MAJORITY — YES` | 2-1. Still a decision. |
| `CALL — YES · decided on conviction` | tied on headcount, one side held it harder |
| `CALL — YES · CASPER breaks the tie` | dead even on both. When the arguments balance exactly, what you want is the deciding fact. |

There is no outcome that hands the question back. Earlier versions reported any disagreement as `DEADLOCK — your call`, which meant 40% of deliberations ended in the council refusing to vote. That was the bug, not the feature.

CONDITIONAL verdicts still require a concrete blocker tied to your actual situation; vague hedges are coerced to ACCEPT.

## Install

One command. Handles Python, Ollama, models, everything:

```bash
curl -fsSL https://raw.githubusercontent.com/x0cero/magi/main/install.sh | bash
```

Or if you prefer doing it yourself:

```bash
pipx install magi-council
ollama pull qwen3:4b && ollama pull dolphin3:8b && ollama pull hermes3:8b
```

The package is `magi-council` because plain `magi` was already taken on PyPI by
an unrelated project. The command you type is still `magi`. To install straight
from source instead: `pipx install git+https://github.com/x0cero/magi`.

Total model footprint: ~12GB, and a warm council answers in seconds. Verify with `magi doctor`.

The seats are deliberately small. Three members run at once against one GPU, so they contend rather than parallelise and the round costs what the slowest seat costs. Measured on an M1 Max: this council answers a round in about 6 seconds, where a 14B-class council took 87. If you have the hardware and want bigger seats, `magi --melchior qwen3:14b` or the config file.

## No spare RAM? Bring a key

Local Ollama is the default identity: your council, your hardware, no API bills. But any council seat can run on a cloud provider instead — prefix the model with the provider name and bring your own key:

```bash
export GROQ_API_KEY=gsk_...     # free tier at console.groq.com
magi --casper "groq/llama-3.3-70b-versatile" "should I move?"
```

Supported prefixes:

| Prefix | Provider | Key env var | Free tier |
|---|---|---|---|
| *(none)* | local Ollama | — | free forever |
| `ollama-cloud/` | [Ollama Cloud](https://ollama.com) | `OLLAMA_API_KEY` | yes |
| `groq/` | [Groq](https://console.groq.com) | `GROQ_API_KEY` | yes |
| `openrouter/` | [OpenRouter](https://openrouter.ai) | `OPENROUTER_API_KEY` | free models |
| `gemini/` | [Google Gemini](https://aistudio.google.com) | `GEMINI_API_KEY` | yes |
| `anthropic/` | [Anthropic](https://console.anthropic.com) | `ANTHROPIC_API_KEY` | no |
| `openai/` | [OpenAI](https://platform.openai.com) | `OPENAI_API_KEY` | no |

Mix and match — a frontier model debating two locals is a legitimately fun council:

```bash
magi --melchior "anthropic/claude-opus-4-8" "should I quit my job?"
```

Make it permanent in `~/.config/magi/config.toml`:

```toml
[models]
casper = "groq/llama-3.3-70b-versatile"

[providers.groq]
api_key = "gsk_..."   # or just export GROQ_API_KEY
```

Bonus: if your local Ollama is signed in to ollama.com, `-cloud` models (`glm-5.2:cloud`, `deepseek-v4-pro:cloud`) work as bare names with zero setup. `magi doctor` checks whichever providers your config actually uses.

## Use

```bash
magi                                    # open the REPL
magi "should I take the job offer?"     # one-shot
magi doctor                             # check Ollama + models
magi stats                              # decision patterns
magi --invite banker "should I move?"   # invite a specialist
```

Inside the REPL:

```
❯  bring a question
❯❯ argue back — the council reconsiders with new info
/new       drop the thread, start fresh
/help      list commands
```

## How it routes your question

A lightweight intake classifier routes each question into one of three flows:

### `decision` — yes/no

Real output, three lenses landing in three different places:

```
❯ i got offered a job that pays 40k more but its at a company whose
  product i think is harmful and the commute is 90 minutes. should i take it

MELCHIOR    CONDITIONAL  ●●●○○
            The 90-minute commute is a secondary constraint that reduces
            the net benefit unless it can be offset.
            MECHANISM: whether they can avoid the harmful product without trade-offs

BALTHASAR   REJECT       ●●●○○
            A salary increase is outweighed by the long-term impact on
            wellbeing, and a long daily commute leads to burnout.
            COST: the irreversible sacrifice of personal values for financial gain

CASPER      ACCEPT       ●●●○○
            You are being asked to enable something you believe is wrong.
            WANT: permission to do something that goes against your values

RESULT: CALL — YES  (1A · 1C · 1R)  ·  dead even, CASPER breaks the tie
```

Three-way split, so it went to conviction, then to the desire lens. Thirty-one seconds.

### `choice` — pick from named options
```
❯ should i write my new ios app in swift or react native
intake: choice question — Swift vs React Native
... [picks per persona, tally]
RESULT: CONSENSUS — Swift  (Swift:3)
```

### `open` — open-ended request for direction
```
❯ i wanna play minecraft but ive been bored of a lot of games
intake: open question
MELCHIOR    RECOMMENDS: Disco Elysium
BALTHASAR   RECOMMENDS: Stardew Valley
CASPER      RECOMMENDS: Stardew Valley
RESULT: PARTIAL OVERLAP — 2/3 agree on one pick  →  your call between 2 options
```

`prediction` questions ("will my startup hit profitability?") are interpreted as decisions: *should they bet on X happening.*

## Specialists

The core MAGI is fixed at three. For higher-stakes questions, invite a specialist:

```
/invite banker      financial reality — cash flow, runway, opportunity cost
/invite therapist   emotional + psychological — what's underneath
/invite lawyer      legal exposure — contracts, liability, downside
/invite coach       career trajectory — what compounds, what's a dead-end
/invite doctor      physical health — body signals, lifestyle impact
```

Specialists join the council and debate alongside the core three. `/dismiss <name>` to remove. They can be invited mid-thread.

## Journal & Stats

Every deliberation auto-saves to `~/.config/magi/journal.jsonl`:

```
/journal                       show recent deliberations
/stats                         decision patterns and analytics
/outcome <id> <what you did>   record what you actually decided
```

## Memory

MAGI learns from your past decisions. Before each deliberation, it searches your journal for similar questions. If it finds a match, the council sees what happened last time:

```
╭──────────────── you've asked this before ─────────────────╮
│  ● 2026-05-02  "should I take the job offer?"  → YES     │
│    ↳ you said: "took it, no regrets"                      │
╰───────────────────────────────────────────────────────────╯
```

After each result, it surfaces patterns: whether you're revisiting a question, which member you tend to follow, and nudges you to record outcomes so the council gets smarter over time. Use `/outcome <id> <what you did>` to close the loop.

## Quiet mode

For scripting, `-q` suppresses all panels and outputs only the verdict line:

```bash
magi -q "should I deploy on Friday?"
# CONSENSUS — YES  (3A · 0C · 0R)

echo "swift or flutter?" | magi -q
# CONSENSUS — Swift  (Swift:3)
```

Works with pipes too: `echo "should I?" | magi -q`

## Config file

Persistent model overrides and auto-invite specialists:

```bash
magi --init-config    # writes ~/.config/magi/config.toml with examples
```

```toml
[models]
melchior = "qwen3:8b"

[specialists]
invite = ["banker"]
```

CLI flags always override the config file.

## Customize

Per-persona model overrides:

```bash
magi --melchior qwen3:8b --balthasar hermes3:8b "..."
```

Or in the REPL:

```
/melchior qwen3:8b
/balthasar llama3.1:8b
```

Override the intake classifier model:

```bash
MAGI_CLASSIFIER_MODEL=llama3.2:1b magi
```

Point at a non-local Ollama:

```bash
OLLAMA_HOST=http://192.168.1.100:11434 magi
```

Raise the context window if you feed the council very long questions (the default keeps models from reserving a KV cache sized to their advertised 128k window, which costs gigabytes for nothing):

```bash
MAGI_NUM_CTX=16384 magi
```

## Is it any good? Run the evals

MAGI ships with its own evaluation harness, because twelve versions of prompt tuning by vibes is how you fix the same bug twice. It runs a fixed suite of questions through the real pipeline and scores the things that make a council good or useless.

```bash
python -m evals run --seed 1 --out evals/runs/mine.json
python -m evals score evals/runs/mine.json -v
python -m evals band evals/runs/seed1.json evals/runs/seed2.json evals/runs/seed3.json
python -m evals compare evals/runs/before.json evals/runs/mine.json
```

**Seed your runs, and measure the spread before you believe a delta.** Without
`--seed`, one run is a single sample of a wide distribution: three runs of
identical code here returned 12, 13 and 17 fabricated premises, and read as a
before-and-after that looks like a regression. `band` scores several repeats
together and prints the smallest change worth believing. `compare` warns you
when it is comparing dice as well as code.

What it measures:

- **fabricated premises** — specifics a member asserted about your situation that your question never contained, separated from the same specifics named as *missing*, which is healthy.
- **lens overlap** — how much the three members repeated each other. This is the metric that matters most. Three models producing one argument is the failure mode of every multi-model council, and the [research on multi-agent debate](https://arxiv.org/pdf/2606.03032) calls it stance homogenization.
- **decisive rate** — how often the council named an answer instead of handing the question back.
- **vagueness, identity leaks, interrogations** — the prose failures the persona prompts exist to prevent.
- **mode accuracy** — whether the intake classifier routed the question correctly.
- **latency** — per question, so a quality change that costs a minute is visible.

Nothing in the harness uses an LLM judge. Every metric is mechanical, so two runs are comparable.

The same 22 questions, v0.12 against v0.13 on the same machine:

| | v0.12 | v0.13 |
|---|---|---|
| routed to the right mode | 41% | 95% |
| landed on an answer | 36% | 100% |
| lens overlap (lower is better) | 0.098 | 0.056 |
| vague phrases | 4 | 1 |
| seconds per question | 171 | 24 |
| whole suite | 63 min | 9 min |

And 0.13.0 against 0.13.1, on the fabrication problem the earlier scorecard could not see:

| | 0.13.0 | 0.13.1 |
|---|---|---|
| answers resting on an invented fact | 6 | 2 |
| questions with any fabrication | 45% | 30% |

Both of those tables predate seeded runs, so read them as directional. Every
number after 0.13.2 comes from a seeded repeat with its band reported.

`evals/runs/baseline-v0.12.json` is committed so you can reproduce the comparison.

## Reproducible runs

Set `MAGI_SEED` to pin the sampler when you need two runs to be comparable:

```bash
MAGI_SEED=1 magi "should i take the contract"
```

Leave it unset for normal use. Varied answers across askings are the point: the
council reading a question differently on a second pass is information about
how close the call is. Cloud providers treat the seed as a hint rather than a
guarantee, so a BYOK council is never as reproducible as a local one.

## Caveats

- **Math is hallucinated.** Small models confidently get arithmetic wrong. For prediction questions involving numbers (runway, breakeven, growth rates), trust the directional verdict, not the specific figures.
- **The council DECIDES.** It will not refuse to vote, even on questions where it lacks information. That's a feature: refusing to decide is the worst outcome. The corollary is that vague questions get vague-but-decisive answers.
- **A tiebreak is not a coin flip, but it is close.** When you see `CALL — ... breaks the tie`, the council genuinely split. The answer stands, but that is the one to argue with.
- **Three is canon.** Don't try to add a fourth core member. Route through specialists instead.

## Why

Coin-flip 2.0. The value is the experience: three independent reads, watching them debate each other by name, surfacing your real preference by friction. It scales from "should I have coffee at 8pm" to "should I quit my job": invite specialists for the heavy ones.

Built explicitly for people who can't decide on their own. The council won't let you wallow.

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
