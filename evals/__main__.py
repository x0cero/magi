"""CLI for the eval harness.

    python -m evals run   --out evals/runs/baseline.json
    python -m evals run   --tag divergent --out evals/runs/quick.json
    python -m evals score evals/runs/baseline.json
    python -m evals compare evals/runs/baseline.json evals/runs/after.json
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
from pathlib import Path

from evals import suite
from evals.metrics import score_run
from evals.runner import run_suite


def cmd_run(args) -> int:
    if args.seed is not None:
        os.environ["MAGI_SEED"] = str(args.seed)

    from magi.core import DEFAULT_MODELS

    models = dict(DEFAULT_MODELS)
    for name in list(models):
        override = getattr(args, name.lower(), None)
        if override:
            models[name] = override

    questions = suite.select(tags=args.tag, ids=args.id)
    if not questions:
        print("no questions matched", file=sys.stderr)
        return 1

    out = Path(args.out)
    print(f"running {len(questions)} questions against {models}")

    def progress(i, total, q):
        print(f"  [{i}/{total}] {q['id']:<20} {q['text'][:56]}", flush=True)

    if args.seed is None:
        print("  (no --seed: this run is one sample of a wide distribution)")
    results = asyncio.run(run_suite(questions, models, out, progress, seed=args.seed))
    card = score_run(results)
    print()
    print_card(card, label=out.name)
    print(f"\nwrote {out}")
    return 0


def _fmt(card: dict) -> list[tuple[str, str]]:
    return [
        ("questions", f"{card['n']}  ({card['errors']} errored)"),
        ("mode accuracy", f"{card['mode_accuracy']:.0%}"),
        ("decisive rate", f"{card['decisive_rate']:.0%}"),
        ("clean (no tiebreak)", f"{card['clean_rate']:.0%}"),
        ("mean lens overlap", f"{card['mean_overlap']:.3f}   (lower is better)"),
        ("worst lens overlap", f"{card['worst_overlap']:.3f}"),
        ("echoing questions", f"{card['echo_questions']}  (at the runtime threshold)"),
        ("longest shared phrase", f"{card['shared_phrase_max']} words"),
        ("unanimous on divergent", f"{card['divergent_unanimous']}/{card['divergent_n']}"),
        ("vague phrases", str(card["vague_total"])),
        ("fabricated premises", f"{card['fabricated_total']}  ({card['fabrication_rate']:.0%} of questions)"),
        ("laundered into fact", str(card["laundered_total"])),
        ("decided on fabrication", str(card["decided_on_fabrication"])),
        ("named as missing", f"{card['demanded_total']}   (healthy, higher is fine)"),
        ("members sent back", str(card["retries_total"])),
        ("identity leaks", str(card["identity_leaks"])),
        ("interrogations", str(card["interrogations"])),
        ("stance changes in debate", str(card["stance_changes"])),
        ("mean seconds", f"{card['mean_elapsed']:.1f}"),
        ("slowest question", f"{card['max_elapsed']:.1f}s"),
        ("total minutes", f"{card['total_elapsed'] / 60:.1f}"),
    ]


def print_card(card: dict, label: str = "") -> None:
    title = f"SCORECARD  {label}".strip()
    print(title)
    print("=" * max(len(title), 44))
    for k, v in _fmt(card):
        print(f"  {k:<26} {v}")


def cmd_score(args) -> int:
    data = json.loads(Path(args.run).read_text())
    card = score_run(data["results"])
    print_card(card, label=Path(args.run).name)
    if args.verbose:
        print("\nper question:")
        header = f"  {'id':<20} {'mode':<11} {'ovlp':>5} {'dec':>4} {'vag':>4} {'leak':>5} {'sec':>6}"
        print(header)
        for p in card["per_question"]:
            dec = "-" if p["decisive"] is None else ("yes" if p["decisive"] else "NO")
            print(
                f"  {str(p['id']):<20} {str(p['mode']):<11} "
                f"{p['echo']['mean_overlap']:>5.2f} {dec:>4} {p['vague_hits']:>4} "
                f"{p['identity_leaks']:>5} {(p['elapsed'] or 0):>6.1f}"
                + ("   ERROR" if p["error"] else "")
            )
    return 0


_LOWER_IS_BETTER = {
    "mean_overlap", "worst_overlap", "echo_questions", "shared_phrase_max",
    "vague_total", "identity_leaks", "interrogations", "divergent_unanimous",
    "mean_elapsed", "max_elapsed", "errors",
    "fabrication_rate", "fabricated_total", "laundered_total", "decided_on_fabrication",
}
_COMPARE_KEYS = [
    "mode_accuracy", "decisive_rate", "clean_rate", "mean_overlap", "worst_overlap",
    "echo_questions", "shared_phrase_max", "divergent_unanimous",
    "vague_total", "identity_leaks", "interrogations", "mean_elapsed",
    "fabrication_rate", "fabricated_total", "laundered_total", "decided_on_fabrication",
]


def cmd_compare(args) -> int:
    before_raw = json.loads(Path(args.before).read_text())
    after_raw = json.loads(Path(args.after).read_text())
    before = score_run(before_raw["results"])
    after = score_run(after_raw["results"])

    # A "WORSE" verdict off two unseeded runs is how a noise band got mistaken
    # for a regression once already.
    if before_raw.get("seed") is None or after_raw.get("seed") is None:
        print("WARNING: at least one run is unseeded, so every verdict below "
              "includes sampling noise.")
        print("         Run `evals band <repeats>` first and ignore any delta "
              "smaller than the spread.\n")
    elif before_raw["seed"] != after_raw["seed"]:
        print(f"WARNING: different seeds ({before_raw['seed']} vs "
              f"{after_raw['seed']}), so you are comparing dice as well as code.\n")

    print(f"{'metric':<24} {'before':>10} {'after':>10}   verdict")
    print("-" * 62)
    for key in _COMPARE_KEYS:
        b, a = before[key], after[key]
        if isinstance(b, float) or isinstance(a, float):
            bs, as_ = f"{b:.3f}", f"{a:.3f}"
        else:
            bs, as_ = str(b), str(a)
        if a == b:
            verdict = "same"
        else:
            improved = (a < b) if key in _LOWER_IS_BETTER else (a > b)
            verdict = "better" if improved else "WORSE"
        print(f"{key:<24} {bs:>10} {as_:>10}   {verdict}")
    return 0


def cmd_band(args) -> int:
    """Score several runs of the SAME code together and print the spread.

    This exists because a single run lied: the same 28 questions on unchanged
    code returned 12, 13 and 17 fabricated premises, and a one-run comparison
    read that as a regression. A delta is only real if it clears the band.
    """
    cards, labels, seeds = [], [], []
    for path in args.runs:
        data = json.loads(Path(path).read_text())
        cards.append(score_run(data["results"]))
        labels.append(Path(path).name)
        seeds.append(data.get("seed"))

    n = len(cards)
    if n < 2:
        print("band needs at least two runs of the same code", file=sys.stderr)
        return 1

    print(f"BAND over {n} runs: {', '.join(labels)}")
    if len(set(seeds)) == 1 and seeds[0] is not None:
        print(f"WARNING: every run used seed {seeds[0]}; identical seeds measure "
              "one sample, not the spread. Vary the seed across repeats.")
    print("=" * 62)
    print(f"{'metric':<24} {'min':>9} {'mean':>9} {'max':>9} {'spread':>9}")
    print("-" * 62)
    for key in _COMPARE_KEYS:
        vals = [c[key] for c in cards]
        lo, hi = min(vals), max(vals)
        mean = statistics.fmean(vals)
        fmt = (lambda v: f"{v:.3f}") if any(isinstance(v, float) for v in vals) else (lambda v: f"{v:g}")
        print(f"{key:<24} {fmt(lo):>9} {fmt(mean):>9} {fmt(hi):>9} {fmt(hi - lo):>9}")
    print()
    print("Read 'spread' as the smallest change worth believing: a delta inside")
    print("it is noise, however much it looks like a regression.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="evals")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run the suite and score it")
    run.add_argument("--out", default="evals/runs/latest.json")
    run.add_argument("--seed", type=int,
                     help="pin the sampler so an A/B measures the code, not the dice")
    run.add_argument("--tag", action="append", help="filter by mode or 'divergent'")
    run.add_argument("--id", action="append", help="run specific question ids")
    run.add_argument("--melchior")
    run.add_argument("--balthasar")
    run.add_argument("--casper")
    run.set_defaults(func=cmd_run)

    score = sub.add_parser("score", help="score a saved run")
    score.add_argument("run")
    score.add_argument("-v", "--verbose", action="store_true")
    score.set_defaults(func=cmd_score)

    band = sub.add_parser("band", help="spread across repeat runs of the same code")
    band.add_argument("runs", nargs="+")
    band.set_defaults(func=cmd_band)

    comp = sub.add_parser("compare", help="compare two saved runs")
    comp.add_argument("before")
    comp.add_argument("after")
    comp.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
