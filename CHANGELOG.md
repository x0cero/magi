# Changelog

## 0.14.0: the console

The interface was a set of tastefully muted panels that could have belonged to
any CLI. It is now the display from the show.

**Three units in the triangle.** MELCHIOR-1 and BALTHASAR-2 on top, CASPER-3
below, dropped into a shared bus. Each unit carries a kanji plate instead of a
word: 審 議 中 while it deliberates, then 可 決, 否 決 or 条 件 付. A unit that
fails to answer reads 応 答 な し. The plate updates live as each member reports,
so you watch the council fill in.

**A decision lands as a stamp**, not as coloured text: a filled plate with the
verdict punched out of it in black, the way the display does it. Unanimity,
a majority and a tiebreak each get their own colour and their own second line
(全 会 一 致, 多 数 決, 決 選).

**Sound.** Cues are synthesised from arithmetic on first run and cached in
`~/.config/magi/sounds/`. Nothing is sampled from the show: that audio is
Khara's and this is a public repo. A unit reporting in clicks, a member sent
back to find its own argument clicks lower, a unanimous council resolves
upward, and a tiebreak deliberately does not resolve. Playback is fire and
forget through whatever the box has, so a machine with no audio tool is silent
rather than broken, and nothing ever waits on a beep.

**Two switches, both read at call time so they can be flipped mid-session:**
`MAGI_SOUND=0` for silence and `MAGI_THEME=classic` for the old panels. The
classic theme is the one to use on a terminal that cannot draw kanji.

The frame is built on measured cell widths rather than string length, because
kanji occupy two terminal cells and Latin one. Every state is asserted to hold
its width, which caught a real tear: a BYOK seat named
`groq/llama-3.3-70b-versatile` is wider than a unit panel and used to push the
right-hand wall out on that one line.

The personas were not touched. The display speaks the show's language; the
council still argues in plain English and is still forbidden from cosplaying it.

## 0.13.2: the same code stopped disagreeing with itself

Three runs of the unchanged 28-question suite returned 12, 13 and 17 fabricated
premises. Read as a before-and-after, that looked like a regression worth
reverting. It was not a regression at all, and chasing it surfaced the reason.

**Council order was whatever the GPU finished first.** Members are consulted
concurrently and collected with `as_completed`, so the positions dict came back
in arrival order. That order is not cosmetic. The round-two prompt lists the
other two members in it, and `_unverified_terms` truncates to the first five
specifics it reads, so a different finishing order named a *different set* of
invented facts back to the council. The pipeline's own fabrication brake was
being aimed by a race. Positions are now pinned to council order the moment
they are collected, and `_unverified_terms` orders them itself as a second
line of defence.

**`MAGI_SEED` pins the sampler.** Unset by default, because varied answers are
the point in normal use. Set it and Ollama's sampling is fixed, which is what
an A/B needs. The two changes compound: before, the same seed still produced
different verdicts, because the race sat downstream of sampling. After, a seeded
run reproduces byte for byte.

**`evals band` reports the spread across repeats**, and `evals compare` now
warns when either run is unseeded instead of printing a confident "WORSE".
Twelve versions of this project were tuned on single runs; the tool now states
the smallest delta worth believing rather than leaving it in a memory file.

**The stance-change metric was counting dictionary order.** It zipped two lists
of verdicts and compared them by position, so it measured MELCHIOR's opening
verdict against whoever sat at the same index in the final dict. It read 2 to 5
while the two dicts happened to agree on order, and 24 to 26 the moment one of
them was sorted, which is how pinning council order appeared to make the
members flip-flop five times as often. It compares by member now.

**Honest result: pinning the order does not make the council more truthful.**
Measured on one machine at seeds 1, 2 and 3, before and after, every metric
overlaps. Fabricated premises ran 18-23 before against 17-22 after, with no
separation anywhere else. What changed is that the after numbers are
reproducible and the before numbers were not. That is the whole claim.

Do not compare any of these figures against the 0.13.1 tables. Those were
measured on a different machine running Ollama 0.32.15, and the same unchanged
code scores about 20 fabricated premises here against about 13 there. The
run-to-run band and the machine-to-machine gap were both larger than any code
change this project has ever measured.

Also in this release, from live use rather than the harness: follow-ups typed at
`❯❯` were being sent through the intake classifier and bounced as noise, which
silently killed the whole argue-back feature (they now inherit the thread's
mode and skip intake); a typo in a member's pick minted a phantom option, so
option matching falls back to a nearest-match; and findings truncated mid-phrase
now cut at a clause boundary.

## 0.13.1 — the council stops making things up

Found by using it. Asked "should i push a database migration to prod at 5pm on
friday" with no other detail, the council voted YES, because MELCHIOR decided
the user had "a 24-hour rollback window with pre-migration testing in staging"
and CASPER decided they had "a planned break" next week. None of that was in
the question. In the next round MELCHIOR cited its own invention as something
BALTHASAR had missed.

A confident answer built on invented premises is worse than a hedge, and every
metric in 0.13.0 graded that transcript as a clean pass.

**Memory was poisoning the council.** The journal fed each deliberation the
council's own past verdicts, and members read them as a track record: asked the
same question a third time, MELCHIOR asserted "a 100% success rate in prior
deployments". A past verdict is this council's own opinion, not evidence. Memory
now shows only what the user asked and what they later recorded actually
happening, and says outright that past verdicts are not precedent.

**Fabrication is now detected and retried.** `magi/grounding.py` flags a novel
specific asserted as an existing fact about the user, distinguishing that from
the same noun named as missing, which is the job: "there is no mention of a
rollback plan" is healthy, "they have a rollback plan" is not. A caught member
is sent back once, exactly like an echo. Negation is scoped per term, because
sentence-wide scope let "the user has already confirmed the migration is ready
with no pending rollbacks" through on the strength of one trailing "no".

**Round two can no longer launder a guess into a fact.** The rebuttal prompt now
carries the user's question verbatim plus a list of specifics nobody actually
established. Costs no extra call.

**Two bugs in 0.13.0's own machinery.** The off-lens retry was computed and then
never dispatched, because the task list iterated `echoes` only — so the lens
territory rules shipped dead. And the eval runner ignored the `revote` event, so
the harness was scoring pre-retry text and could not see its own fixes working.

Measured like-for-like on the 22 shared suite questions:

| | 0.13.0 | 0.13.1 |
|---|---|---|
| answers resting on an invented fact | 6 | 2 |
| fabricated premises | 16 | 12 |
| questions with any fabrication | 45% | 30% |
| decisive rate | 100% | 100% |
| seconds per question | 24 | 34 |

Six deliberately sparse questions were added to the suite ("should i take the
15k", "should i tell her") because a question with nothing in it is where a
model either admits the gap or invents one.

Honest limits: retries fired 20 times and reduced fabrication in 7 of them.
Laundering went from 1 to 3. The detector works from a curated lexicon plus
figures, so an invention in a domain it has never seen still gets through, and
"you want this money to pursue your dream of opening a bakery" scores zero.

## 0.13.0 — the council decides again

Same 22-question suite, same machine, v0.12 against v0.13:

| | v0.12 | v0.13 |
|---|---|---|
| routed to the right mode | 41% | 95% |
| landed on an answer | 36% | 100% |
| lens overlap (lower is better) | 0.098 | 0.056 |
| worst single overlap | 0.255 | 0.162 |
| vague phrases | 4 | 1 |
| identity leaks | 2 | 1 |
| seconds per question | 171 | 24 |
| member failures | 0 | 0 |

The three lenses had collapsed into one voice, and the council had quietly
stopped deciding. Both are fixed, and there is now an eval harness so the next
change can be proven instead of felt.

### Lens collapse

Three models running three lens prompts were producing the same argument. On
"should i quit my warehouse job", MELCHIOR and BALTHASAR both answered "two
months of savings is insufficient runway" and CASPER, whose entire job is
desire and identity, returned a generic risk paragraph.

- **Every member now owes a finding only its lens can produce** — MELCHIOR a
  MECHANISM, BALTHASAR a COST, CASPER a WANT. The instruction rides in that
  member's own JSON schema, so constrained decoding enforces it per member.
- **Each lens is told what it does not own.** Runway math belongs to MELCHIOR;
  BALTHASAR and CASPER are told not to make that argument because it is
  already covered.
- **Asymmetric priors.** MELCHIOR weighs evidence over narrative, BALTHASAR
  irreversibility over upside, CASPER regret-of-not-doing over risk-of-doing.
  The council now brackets the question instead of piling on caution.
- **Anti-echo retry.** After round one, any member whose reasoning overlaps
  another's is sent back once, at higher temperature, with the other member's
  text quoted, and told to find its own argument. The retry is only accepted
  if it actually stopped echoing. Runs in decision and choice modes.
- **Off-lens retry.** The prompt rules alone did not hold on small models:
  BALTHASAR kept reaching for runway and CASPER kept saying "it's risky",
  which are MELCHIOR's arguments. A member caught using another lens's
  vocabulary is sent back the same way.
- **Trimming that bites.** "1-3 sentences" and "under 20 words" were
  suggestions a chatty model ignored, and the tail of a long answer is where
  sign-offs and invented personal experience live (one member claimed to have
  personally enjoyed a game it recommended). Reasoning is now trimmed to three
  sentences and findings to one claim, deterministically.
- **Recommend mode is three members again.** The vagueness validator rejected
  category-shaped answers, and the member then dropped out of the council
  silently — the data lens was missing from every single open question. There
  is now one corrective retry that quotes the rejected answer back.

### Decisiveness

40% of all logged deliberations ended in `DEADLOCK — your call`, and 18 of
those 23 had a clear 2-1 majority the council simply refused to call.

- **Majority rules.** 2-1 is `MAJORITY`, a decision.
- **Confidence, 1-5, from every member.** A genuine tie is decided on total
  conviction, which is [better than flat majority vote](https://arxiv.org/pdf/2606.13591).
- **A tie on conviction goes to CASPER.** When the arguments balance exactly,
  what you want is the deciding fact.
- There is no longer any outcome that hands the question back.

### Routing was dead

The intake classifier from v0.11 had stopped working entirely. It runs on a
reasoning model, so the `think` bug below made it return empty content on every
call, and `classify_safe` silently fell back to `decision`. Every question went
through the yes/no flow: choice mode, recommend mode and noise rejection were
all unreachable, and "hey" got a two-minute deliberation. Routing accuracy on
the eval suite was 41%, which is exactly what you get when everything is
classified the same way.

### Speed

- **Smaller default seats.** Three members run concurrently against one GPU, so
  they contend rather than parallelise and the round costs what the slowest
  seat costs. Measured warm on an M1 Max: qwen3:14b + phi4 + hermes3:8b took
  87s per round; qwen3:4b + dolphin3:8b + hermes3:8b takes 6.4s. Footprint
  drops from ~25GB to ~12GB. Bigger seats are one flag away.
- **Fixed `think`.** Ollama takes `think` as a top-level field, not an option.
  MAGI was passing it inside `options`, where it is silently ignored, so
  reasoning models spent their entire 1200-token budget on hidden
  chain-of-thought. Measured on qwen3:4b: 1200 tokens and empty content
  before, 100 tokens and a clean verdict after.
- **Pinned the context window** (`MAGI_NUM_CTX`, default 8192). `hermes3:8b`
  was reserving 21GB of KV cache to match its advertised 128k window.
- **Two rounds, not three.** Measured across the eval suite: three rounds
  changed zero verdicts while burning two thirds of the wall clock. One debate
  round keeps members answering each other by name and drops the restating.
- **Stop early when nobody moves.** If a round changes no positions, the next
  round is three models repeating themselves.

### Evals

New `evals/` harness. A fixed suite runs through the real pipeline and scores
lens overlap, decisive rate, vagueness, identity leaks, interrogations, mode
accuracy and latency. Every metric is mechanical, so runs are comparable.

    python -m evals run --out evals/runs/mine.json
    python -m evals compare evals/runs/before.json evals/runs/mine.json

### Also

- `[options] max_rounds` in config.toml was documented but never read. It is
  wired up now, clamped to 1-6.
- Journal, stats and pattern detection understand the new outcomes; pre-0.13
  entries still render.
