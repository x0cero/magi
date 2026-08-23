from __future__ import annotations

from rich.box import HEAVY, ROUNDED, SIMPLE
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from magi.core import (
    ChoiceRebuttal,
    ChoiceResponse,
    PersonaResponse,
    Rebuttal,
    RecommendRebuttal,
    RecommendResponse,
    Verdict,
)
from magi.personas import lens_field_label

ACCENT = "#d4874e"

MEMBER_COLOR = {
    "MELCHIOR": "#c47a5a",
    "BALTHASAR": "#6b8cae",
    "CASPER": "#7da87b",
    "BANKER": "#c4a35a",
    "THERAPIST": "#a07db5",
    "LAWYER": "#8a8a8a",
    "COACH": "#c48a5a",
    "DOCTOR": "#5a9e9c",
}

MEMBER_ICON = {
    "MELCHIOR": "◆",
    "BALTHASAR": "◇",
    "CASPER": "○",
    "BANKER": "$",
    "THERAPIST": "♡",
    "LAWYER": "§",
    "COACH": "↗",
    "DOCTOR": "+",
}

VERDICT_COLOR = {
    Verdict.ACCEPT: "#8abf7a",
    Verdict.REJECT: "#c4685a",
    Verdict.CONDITIONAL: "#c4a35a",
}

VERDICT_ICON = {
    Verdict.ACCEPT: "▌YES",
    Verdict.REJECT: "▌NO",
    Verdict.CONDITIONAL: "▌IF",
}

CHOICE_COLOR = "#6b9ec4"
RECOMMEND_COLOR = "#a07db5"


def _mc(name: str) -> str:
    return MEMBER_COLOR.get(name, "white")


def _mi(name: str) -> str:
    return MEMBER_ICON.get(name, "·")


BANNER = f"""[bold {ACCENT}]
    ███╗   ███╗ █████╗  ██████╗ ██╗
    ████╗ ████║██╔══██╗██╔════╝ ██║
    ██╔████╔██║███████║██║  ███╗██║
    ██║╚██╔╝██║██╔══██║██║   ██║██║
    ██║ ╚═╝ ██║██║  ██║╚██████╔╝██║
    ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝[/bold {ACCENT}]
"""


HELP_TEXT = f"""[bold]commands[/bold]
  [{ACCENT}]/help[/{ACCENT}]                  show this help
  [{ACCENT}]/new[/{ACCENT}]                   start a fresh deliberation
  [{ACCENT}]/models[/{ACCENT}]                show current model assignments
  [{ACCENT}]/specialists[/{ACCENT}]           list specialists you can invite
  [{ACCENT}]/invite[/{ACCENT}] <name>         invite a specialist (banker, therapist, lawyer, coach, doctor)
  [{ACCENT}]/dismiss[/{ACCENT}] <name>        remove a specialist from the council
  [{ACCENT}]/melchior[/{ACCENT}] <model>      assign a different model to a member
  [{ACCENT}]/reset[/{ACCENT}]                 reset to defaults; dismiss all specialists
  [{ACCENT}]/journal[/{ACCENT}]               show your past deliberations
  [{ACCENT}]/stats[/{ACCENT}]                 decision patterns and analytics
  [{ACCENT}]/outcome[/{ACCENT}] <id> <text>   record what you actually did/didn't do
  [{ACCENT}]/clear[/{ACCENT}]                 clear the screen
  [{ACCENT}]/exit[/{ACCENT}]                  exit the MAGI

[bold]how this works[/bold]
  [{ACCENT}]❯[/{ACCENT}]   bring a question, the council deliberates
  [{ACCENT}]❯❯[/{ACCENT}]  argue back, they reconsider with new info
  [{ACCENT}]/new[/{ACCENT}]  drop the thread, start fresh

[bold]deliberation[/bold]
  round 1    each member votes independently from their lens
  round 2+   they read each other, argue, verdicts can shift
             consensus or 3 rounds max

[bold]outcomes[/bold]
  [#8abf7a]CONSENSUS[/#8abf7a]   all agree, clean answer
  [#c4a35a]DEADLOCK[/#c4a35a]    could not agree, your call
"""


def print_banner(console: Console, models: dict[str, str]) -> None:
    console.print(BANNER)
    parts = Text("    ")
    for name in ("MELCHIOR", "BALTHASAR", "CASPER"):
        if name != "MELCHIOR":
            parts.append("  ·  ", style="dim")
        parts.append(f"{_mi(name)} ", style=f"bold {_mc(name)}")
        parts.append(name, style=f"bold {_mc(name)}")
        parts.append(f" [{models.get(name, '?')}]", style="dim")
    console.print(parts)
    console.print(f"    [dim]the council convenes[/dim]  [{ACCENT}]/help[/{ACCENT}] [dim]for commands[/dim]\n")


def print_models(console: Console, models: dict[str, str]) -> None:
    text = Text()
    for name in ("MELCHIOR", "BALTHASAR", "CASPER"):
        if name in models:
            text.append(f"  {_mi(name)} ", style=f"bold {_mc(name)}")
            text.append(f"{name:<10}", style=f"bold {_mc(name)}")
            text.append(f"  {models[name]}\n", style="dim")
    console.print(Panel(text, title=f"[bold {ACCENT}]models[/bold {ACCENT}]", border_style="dim", box=ROUNDED))


def _sanitize_error(exc: Exception) -> str:
    msg = str(exc)
    if "http://" in msg or "https://" in msg:
        return type(exc).__name__
    return f"{type(exc).__name__}: {msg[:120]}"


def _verdict_badge(verdict: Verdict) -> Text:
    t = Text()
    t.append(f" {VERDICT_ICON[verdict]} ", style=f"bold {VERDICT_COLOR[verdict]}")
    return t


def _member_tag(name: str) -> str:
    return f"[bold {_mc(name)}]{_mi(name)} {name}[/bold {_mc(name)}]"


def _round_rule(console: Console, round_num: int, label: str) -> None:
    console.print()
    console.print(Rule(f"[bold {ACCENT}] ROUND {round_num} [/bold {ACCENT}] [dim]{label}[/dim]", style=ACCENT))
    console.print()


# Decision mode

def vote_status_panel(statuses: dict[str, str], results: dict) -> Panel:
    text = Text()
    for name in statuses:
        result = results.get(name)
        if result is None:
            mark, style = "◌", "dim"
        elif isinstance(result, Exception):
            mark, style = "✗", "red"
        else:
            mark, style = "●", VERDICT_COLOR[result.verdict]
        text.append(f"  {mark} ", style=f"bold {style}")
        text.append(f"{name:<10} ", style=f"{_mc(name)}")
        text.append(f" {statuses[name]}\n", style="dim")
    return Panel(text, title=f"[bold {ACCENT}]voting[/bold {ACCENT}]", border_style=ACCENT, box=SIMPLE)


def debate_status_panel(statuses: dict[str, str], rebuttals: dict, round_num: int) -> Panel:
    text = Text()
    for name in statuses:
        result = rebuttals.get(name)
        if result is None:
            mark, style = "◌", "dim"
        elif isinstance(result, Exception):
            mark, style = "✗", "red"
        else:
            mark, style = "●", VERDICT_COLOR[result.final_verdict]
        text.append(f"  {mark} ", style=f"bold {style}")
        text.append(f"{name:<10} ", style=f"{_mc(name)}")
        text.append(f" {statuses[name]}\n", style="dim")
    return Panel(text, title=f"[bold {ACCENT}]round {round_num}[/bold {ACCENT}]", border_style=ACCENT, box=SIMPLE)


def _conviction(level: int | None) -> str:
    """Conviction as filled dots — how hard this member would defend the call."""
    level = max(1, min(5, int(level or 3)))
    return "●" * level + "○" * (5 - level)


def _append_finding(body: Text, name: str, result) -> None:
    """The one thing only this member's lens produced."""
    finding = getattr(result, "lens_finding", "") or ""
    if not finding:
        return
    body.append("\n\n")
    body.append(f"  {lens_field_label(name)}: ", style=f"bold {_mc(name)}")
    body.append(finding)


def _persona_panel(name: str, result: PersonaResponse | Exception) -> Panel:
    if isinstance(result, Exception):
        body = Text(f"  ✗ {_sanitize_error(result)}", style="red")
        return Panel(body, title=_member_tag(name), border_style="red", box=HEAVY)

    color = VERDICT_COLOR[result.verdict]
    body = Text()
    body.append(f"  {VERDICT_ICON[result.verdict]} ", style=f"bold {color}")
    body.append(f"{result.verdict.value}", style=f"bold {color}")
    body.append(f"   {_conviction(result.confidence)}\n\n", style="dim")
    body.append(f"  {result.reasoning}")
    _append_finding(body, name, result)
    if result.verdict == Verdict.CONDITIONAL and result.condition:
        body.append("\n\n")
        body.append("  ONLY IF: ", style=f"bold {color}")
        body.append(result.condition)
    return Panel(body, title=_member_tag(name), border_style=_mc(name), box=HEAVY, padding=(0, 1))


def _debate_panel(
    name: str,
    previous_verdict: Verdict | None,
    rebuttal: Rebuttal | Exception | None,
    round_num: int,
) -> Panel:
    if isinstance(rebuttal, Exception):
        body = Text(f"  ✗ {_sanitize_error(rebuttal)}", style="red")
        return Panel(body, title=_member_tag(name), border_style="red", box=HEAVY)

    if rebuttal is None:
        body = Text("  (silent this round)", style="dim")
        return Panel(body, title=_member_tag(name), border_style="dim", box=SIMPLE)

    color = VERDICT_COLOR[rebuttal.final_verdict]
    body = Text()
    body.append(f"  {rebuttal.response}\n\n")
    body.append(f"  {VERDICT_ICON[rebuttal.final_verdict]} ", style=f"bold {color}")
    body.append(f"{rebuttal.final_verdict.value}", style=f"bold {color}")
    if previous_verdict is not None and rebuttal.final_verdict != previous_verdict:
        body.append(f"  ← was {previous_verdict.value}", style="bold yellow")
    elif previous_verdict is not None:
        body.append("  (held)", style="dim")
    if rebuttal.final_verdict == Verdict.CONDITIONAL and rebuttal.condition:
        body.append("\n  ONLY IF: ", style=f"bold {color}")
        body.append(rebuttal.condition)
    return Panel(body, title=_member_tag(name), subtitle=f"[dim]round {round_num}[/dim]", border_style=_mc(name), box=HEAVY, padding=(0, 1))


def render_initial_votes(votes: dict, console: Console) -> None:
    for name, result in votes.items():
        console.print(_persona_panel(name, result))


def render_debate_round(
    round_num: int,
    rebuttals: dict,
    previous_verdicts: dict[str, Verdict],
    console: Console,
) -> None:
    for name, rebuttal in rebuttals.items():
        prev = previous_verdicts.get(name)
        console.print(_debate_panel(name, prev, rebuttal, round_num))


OUTCOME_STYLE = {
    "consensus": ("#8abf7a", "◈"),   # everyone agreed
    "picks": ("#8abf7a", "◈"),
    "majority": ("#b0a878", "◈"),    # 2-1: still a decision
    "conviction": ("#c4a35a", "◆"),  # tied on heads, decided on conviction
    "tiebreak": ("#c4a35a", "◆"),    # dead even, desire lens broke it
    "deadlock": ("#c4a35a", "◇"),    # legacy journal entries only
    "split": ("#c4a35a", "◇"),
}


def render_synthesis(synthesis: str, outcome: str, console: Console) -> None:
    color, icon = OUTCOME_STYLE.get(outcome, ("red", "✗"))

    console.print()
    console.print(Rule(style=color))
    result_text = Text(justify="center")
    result_text.append(f"\n  {icon}  ", style=f"bold {color}")
    result_text.append(synthesis, style=f"bold {color}")
    result_text.append(f"  {icon}  \n", style=f"bold {color}")
    console.print(result_text)
    console.print(Rule(style=color))


# Choice mode

def choice_vote_status_panel(statuses: dict[str, str], results: dict) -> Panel:
    text = Text()
    for name in statuses:
        result = results.get(name)
        if result is None:
            mark, style = "◌", "dim"
        elif isinstance(result, Exception):
            mark, style = "✗", "red"
        else:
            mark, style = "●", CHOICE_COLOR
        text.append(f"  {mark} ", style=f"bold {style}")
        text.append(f"{name:<10} ", style=f"{_mc(name)}")
        text.append(f" {statuses[name]}\n", style="dim")
    return Panel(text, title=f"[bold {ACCENT}]picking[/bold {ACCENT}]", border_style=ACCENT, box=SIMPLE)


def choice_debate_status_panel(statuses: dict[str, str], rebuttals: dict, round_num: int) -> Panel:
    text = Text()
    for name in statuses:
        result = rebuttals.get(name)
        if result is None:
            mark, style = "◌", "dim"
        elif isinstance(result, Exception):
            mark, style = "✗", "red"
        else:
            mark, style = "●", CHOICE_COLOR
        text.append(f"  {mark} ", style=f"bold {style}")
        text.append(f"{name:<10} ", style=f"{_mc(name)}")
        text.append(f" {statuses[name]}\n", style="dim")
    return Panel(text, title=f"[bold {ACCENT}]round {round_num}[/bold {ACCENT}]", border_style=ACCENT, box=SIMPLE)


def _choice_panel(name: str, result: ChoiceResponse | Exception) -> Panel:
    if isinstance(result, Exception):
        body = Text(f"  ✗ {_sanitize_error(result)}", style="red")
        return Panel(body, title=_member_tag(name), border_style="red", box=HEAVY)

    body = Text()
    body.append("  ▌ ", style=f"bold {CHOICE_COLOR}")
    body.append(f"{result.chosen_option}", style=f"bold {CHOICE_COLOR}")
    body.append(f"   {_conviction(result.confidence)}\n\n", style="dim")
    body.append(f"  {result.reasoning}")
    _append_finding(body, name, result)
    return Panel(body, title=_member_tag(name), border_style=_mc(name), box=HEAVY, padding=(0, 1))


def _choice_debate_panel(
    name: str,
    previous_choice: str | None,
    rebuttal: ChoiceRebuttal | Exception | None,
    round_num: int,
) -> Panel:
    if isinstance(rebuttal, Exception):
        body = Text(f"  ✗ {_sanitize_error(rebuttal)}", style="red")
        return Panel(body, title=_member_tag(name), border_style="red", box=HEAVY)

    if rebuttal is None:
        body = Text("  (silent this round)", style="dim")
        return Panel(body, title=_member_tag(name), border_style="dim", box=SIMPLE)

    body = Text()
    body.append(f"  {rebuttal.response}\n\n")
    body.append("  ▌ ", style=f"bold {CHOICE_COLOR}")
    body.append(rebuttal.final_choice, style=f"bold {CHOICE_COLOR}")
    if previous_choice is not None and rebuttal.final_choice != previous_choice:
        body.append(f"  ← was {previous_choice}", style="bold yellow")
    elif previous_choice is not None:
        body.append("  (held)", style="dim")
    return Panel(body, title=_member_tag(name), subtitle=f"[dim]round {round_num}[/dim]", border_style=_mc(name), box=HEAVY, padding=(0, 1))


def render_initial_choices(choices: dict, console: Console) -> None:
    for name, result in choices.items():
        console.print(_choice_panel(name, result))


def render_choice_debate_round(
    round_num: int,
    rebuttals: dict,
    previous_choices: dict[str, str],
    console: Console,
) -> None:
    for name, rebuttal in rebuttals.items():
        prev = previous_choices.get(name)
        console.print(_choice_debate_panel(name, prev, rebuttal, round_num))


def render_intake(question_class: str, options: list[str], console: Console) -> None:
    if question_class == "choice" and options:
        label = " vs ".join(options)
    else:
        label = question_class
    t = Text("  ")
    t.append("▸ ", style=ACCENT)
    t.append(label, style="dim")
    console.print(t)


# Recommend mode

def recommend_vote_status_panel(statuses: dict[str, str], results: dict) -> Panel:
    text = Text()
    for name in statuses:
        result = results.get(name)
        if result is None:
            mark, style = "◌", "dim"
        elif isinstance(result, Exception):
            mark, style = "✗", "red"
        else:
            mark, style = "●", RECOMMEND_COLOR
        text.append(f"  {mark} ", style=f"bold {style}")
        text.append(f"{name:<10} ", style=f"{_mc(name)}")
        text.append(f" {statuses[name]}\n", style="dim")
    return Panel(text, title=f"[bold {ACCENT}]recommending[/bold {ACCENT}]", border_style=ACCENT, box=SIMPLE)


def recommend_debate_status_panel(statuses: dict[str, str], rebuttals: dict, round_num: int) -> Panel:
    text = Text()
    for name in statuses:
        result = rebuttals.get(name)
        if result is None:
            mark, style = "◌", "dim"
        elif isinstance(result, Exception):
            mark, style = "✗", "red"
        else:
            mark, style = "●", RECOMMEND_COLOR
        text.append(f"  {mark} ", style=f"bold {style}")
        text.append(f"{name:<10} ", style=f"{_mc(name)}")
        text.append(f" {statuses[name]}\n", style="dim")
    return Panel(text, title=f"[bold {ACCENT}]round {round_num}[/bold {ACCENT}]", border_style=ACCENT, box=SIMPLE)


def _recommend_panel(name: str, result: RecommendResponse | Exception) -> Panel:
    if isinstance(result, Exception):
        body = Text(f"  ✗ {_sanitize_error(result)}", style="red")
        return Panel(body, title=_member_tag(name), border_style="red", box=HEAVY)

    body = Text()
    body.append("  ▌ ", style=f"bold {RECOMMEND_COLOR}")
    body.append(f"{result.recommendation}\n\n", style=f"bold {RECOMMEND_COLOR}")
    body.append(f"  {result.reasoning}")
    return Panel(body, title=_member_tag(name), border_style=_mc(name), box=HEAVY, padding=(0, 1))


def _recommend_debate_panel(
    name: str,
    previous_rec: str | None,
    rebuttal: RecommendRebuttal | Exception | None,
    round_num: int,
) -> Panel:
    if isinstance(rebuttal, Exception):
        body = Text(f"  ✗ {_sanitize_error(rebuttal)}", style="red")
        return Panel(body, title=_member_tag(name), border_style="red", box=HEAVY)

    if rebuttal is None:
        body = Text("  (silent this round)", style="dim")
        return Panel(body, title=_member_tag(name), border_style="dim", box=SIMPLE)

    body = Text()
    body.append(f"  {rebuttal.response}\n\n")
    body.append("  ▌ ", style=f"bold {RECOMMEND_COLOR}")
    body.append(rebuttal.final_recommendation, style=f"bold {RECOMMEND_COLOR}")
    if previous_rec is not None and rebuttal.final_recommendation.lower().strip() != previous_rec.lower().strip():
        body.append(f"\n  ← was: {previous_rec}", style="bold yellow")
    elif previous_rec is not None:
        body.append("  (held)", style="dim")
    return Panel(body, title=_member_tag(name), subtitle=f"[dim]round {round_num}[/dim]", border_style=_mc(name), box=HEAVY, padding=(0, 1))


def render_initial_recommendations(recs: dict, console: Console) -> None:
    for name, result in recs.items():
        console.print(_recommend_panel(name, result))


def render_recommend_debate_round(
    round_num: int,
    rebuttals: dict,
    previous_recs: dict[str, str],
    console: Console,
) -> None:
    for name, rebuttal in rebuttals.items():
        prev = previous_recs.get(name)
        console.print(_recommend_debate_panel(name, prev, rebuttal, round_num))


def print_help(console: Console) -> None:
    console.print(Panel(HELP_TEXT, border_style="dim", box=ROUNDED))


def warmup_status_panel(statuses: dict[str, tuple[str, str]]) -> Panel:
    """statuses[name] = (model_id, state). state ∈ {'loading', 'ready', 'failed: ...'}."""
    text = Text()
    for name, (model, state) in statuses.items():
        if state == "ready":
            mark = "●"
        elif state == "loading":
            mark = "◌"
        else:
            mark = "✗"
        text.append(f"  {mark} ", style=f"bold {_mc(name)}")
        text.append(f"{name:<10} ", style=f"bold {_mc(name)}")
        text.append(f" {model}  ", style="dim")
        if state == "ready":
            text.append("ready\n", style=f"dim {_mc(name)}")
        elif state == "loading":
            text.append("loading\n", style="dim")
        else:
            text.append(f"{state}\n", style="dim red")
    return Panel(text, title=f"[bold {ACCENT}]warming council[/bold {ACCENT}]", border_style=ACCENT, box=SIMPLE)


def render_journal(entries: list[dict], console: Console) -> None:
    if not entries:
        console.print("[dim]journal is empty, your deliberations will be logged here[/dim]")
        return
    text = Text()
    for entry in entries:
        ts = entry.get("timestamp", "")[:16].replace("T", " ")
        outcome = entry.get("outcome", "?")
        if outcome in ("consensus", "picks"):
            icon, oc = "●", "#8abf7a"
        elif outcome == "majority":
            icon, oc = "◐", "#b0a878"
        elif outcome in ("conviction", "tiebreak"):
            icon, oc = "◆", "#c4a35a"
        elif outcome in ("deadlock", "split"):
            icon, oc = "◇", "#c4a35a"
        else:
            icon, oc = "·", "dim"
        text.append(f"  {icon} ", style=f"bold {oc}")
        text.append(f"{entry.get('id', '?'):<8} ", style=f"{ACCENT}")
        text.append(f"{ts}\n", style="dim")
        text.append(f"    {entry.get('question', '')[:90]}\n", style="italic")
        text.append(f"    {entry.get('synthesis', '')}\n", style="dim")
        if entry.get("user_outcome"):
            text.append(f"    ↳ {entry['user_outcome']}\n", style="#8abf7a")
        text.append("\n")
    console.print(Panel(text, title=f"[bold {ACCENT}]journal[/bold {ACCENT}]", border_style="dim", box=ROUNDED))


def render_stats(entries: list[dict], console: Console) -> None:
    if not entries:
        console.print("[dim]no deliberations yet[/dim]")
        return

    total = len(entries)
    consensus_count = sum(1 for e in entries if e.get("outcome") == "consensus")
    majority_count = sum(1 for e in entries if e.get("outcome") == "majority")
    close_count = sum(1 for e in entries if e.get("outcome") in ("conviction", "tiebreak"))
    # pre-0.13 journal entries, when a 2-1 vote was reported as a hung council
    deadlock_count = sum(1 for e in entries if e.get("outcome") in ("deadlock", "split"))
    picks_count = sum(1 for e in entries if e.get("outcome") == "picks")
    other_count = total - consensus_count - majority_count - close_count - deadlock_count - picks_count
    outcomes_recorded = sum(1 for e in entries if e.get("user_outcome"))

    avg_rounds = 0
    rounds_entries = [e for e in entries if e.get("rounds")]
    if rounds_entries:
        avg_rounds = sum(e["rounds"] for e in rounds_entries) / len(rounds_entries)

    text = Text()
    text.append(f"  total       {total}\n", style="bold")
    text.append(f"  consensus   {consensus_count}", style="#8abf7a")
    if total > 0:
        text.append(f"  ({consensus_count * 100 // total}%)", style="dim")
    text.append("\n")
    if majority_count:
        text.append(f"  majority    {majority_count}", style="#b0a878")
        text.append(f"  ({majority_count * 100 // total}%)\n", style="dim")
    if close_count:
        text.append(f"  too close   {close_count}", style="#c4a35a")
        text.append(f"  ({close_count * 100 // total}%)\n", style="dim")
    if deadlock_count:
        text.append(f"  deadlock    {deadlock_count}", style="#c4a35a")
        text.append(f"  ({deadlock_count * 100 // total}%)", style="dim")
        text.append("  legacy\n", style="dim")
    if picks_count:
        text.append(f"  open        {picks_count}\n", style=RECOMMEND_COLOR)
    if other_count:
        text.append(f"  other       {other_count}\n", style="dim")
    text.append(f"  avg rounds  {avg_rounds:.1f}\n", style="dim")
    text.append(f"  recorded    {outcomes_recorded}/{total}\n", style="dim")

    console.print(Panel(text, title=f"[bold {ACCENT}]stats[/bold {ACCENT}]", border_style="dim", box=ROUNDED))

    close = [e for e in entries if e.get("outcome") in ("deadlock", "split", "conviction", "tiebreak")]
    if len(close) >= 3:
        text2 = Text()
        for e in close[:10]:
            ts = e.get("timestamp", "")[:10]
            text2.append(f"  {ts}  ", style="dim")
            text2.append(f"{e.get('question', '')[:80]}\n", style="italic")
        console.print(Panel(text2, title="[bold #c4a35a]the ones that split the council[/bold #c4a35a]", border_style="#c4a35a", box=ROUNDED))


def render_memory_hits(hits: list, console: Console) -> None:
    if not hits:
        return
    text = Text()
    for h in hits:
        text.append("  ● ", style=f"dim {ACCENT}")
        text.append(f"{h.timestamp}  ", style="dim")
        text.append(f'"{h.question[:70]}"', style="italic")
        text.append(f"  → {h.outcome}\n", style="dim")
        if h.user_outcome:
            text.append(f"    ↳ you said: \"{h.user_outcome}\"\n", style=f"{ACCENT}")
    console.print(Panel(text, title=f"[bold {ACCENT}]you've asked this before[/bold {ACCENT}]", border_style="dim", box=ROUNDED))


def render_patterns(patterns, console: Console) -> None:
    lines: list[str] = []
    if patterns.repeat_question:
        lines.append("you've circled back to this one")
    if patterns.deadlock_streak >= 3:
        lines.append(f"the last {patterns.deadlock_streak} questions split the council down the middle")
    if patterns.top_followed_member:
        color = _mc(patterns.top_followed_member)
        icon = _mi(patterns.top_followed_member)
        lines.append(f"you tend to follow [{color}]{icon} {patterns.top_followed_member}[/{color}] ({patterns.top_followed_count} times)")
    if patterns.outcomes_recorded > 0 and patterns.total_deliberations > 5:
        rate = patterns.outcomes_recorded * 100 // patterns.total_deliberations
        if rate < 30:
            lines.append(f"only {rate}% of your decisions have recorded outcomes, /outcome helps the council learn")
    if not lines:
        return
    text = Text()
    for line in lines:
        text.append("  ▸ ", style=f"dim {ACCENT}")
    console.print()
    for line in lines:
        console.print(f"  [{ACCENT}]▸[/{ACCENT}] [dim]{line}[/dim]")
