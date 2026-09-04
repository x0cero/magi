
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from magi import journal, sound
from magi.core import (
    DEFAULT_MODELS,
    ChoiceRebuttal,
    ChoiceResponse,
    Deliberation,
    OllamaUnavailable,
    PersonaResponse,
    Rebuttal,
    RecommendRebuttal,
    RecommendResponse,
    Verdict,
    iterative_choose,
    iterative_deliberate,
    iterative_recommend,
    synthesize,
    synthesize_choice,
    synthesize_recommend,
)
from magi.intake import Classification, QuestionClass, classify_safe
from magi.memory import build_context, detect_patterns, search
from magi.personas import (
    PERSONAS,
    SPECIALIST_DEFAULT_MODELS,
    SPECIALIST_DESCRIPTIONS,
    SPECIALISTS,
    is_core_member,
)
from magi.render import (
    choice_debate_status_panel,
    choice_vote_status_panel,
    debate_status_panel,
    print_banner,
    print_help,
    print_models,
    recommend_debate_status_panel,
    recommend_vote_status_panel,
    render_choice_debate_round,
    render_debate_round,
    render_initial_choices,
    render_initial_recommendations,
    render_initial_votes,
    render_intake,
    render_journal,
    render_memory_hits,
    render_patterns,
    render_recommend_debate_round,
    render_stats,
    render_synthesis,
    vote_status_panel,
    warmup_status_panel,
)
from magi.warmup import warmup_models


async def warm_council(models: dict[str, str], console: Console) -> None:
    """Pre-load models. Raises OllamaUnavailable if Ollama is unreachable."""
    import httpx
    statuses: dict[str, tuple[str, str]] = {n: (m, "loading") for n, m in models.items()}
    all_connect_failed = True
    with Live(warmup_status_panel(statuses), console=console, refresh_per_second=4) as live:
        async for name, model, err in warmup_models(models):
            if err is None:
                all_connect_failed = False
            elif not isinstance(err, httpx.ConnectError):
                all_connect_failed = False
            statuses[name] = (model, "ready" if err is None else f"failed: {type(err).__name__}")
            live.update(warmup_status_panel(statuses))
    console.print()
    if all_connect_failed and models:
        raise OllamaUnavailable()


def _print_council_roster(console: Console, models: dict[str, str]) -> None:
    text = Text()
    text.append("CORE\n", style="bold cyan")
    for name in ("MELCHIOR", "BALTHASAR", "CASPER"):
        if name in models:
            text.append(f"  {name:<11} ", style="bold")
            text.append(f"{models[name]}\n", style="dim")

    invited = [n for n in models if not is_core_member(n)]
    if invited:
        text.append("\nINVITED SPECIALISTS\n", style="bold magenta")
        for name in invited:
            desc = SPECIALIST_DESCRIPTIONS.get(name, "")
            text.append(f"  {name:<11} ", style="bold")
            text.append(f"{models[name]}", style="dim")
            if desc:
                text.append(f"  — {desc}", style="dim italic")
            text.append("\n")

    available = [s for s in SPECIALISTS if s not in models]
    if available:
        text.append("\nAVAILABLE TO INVITE\n", style="bold")
        for name in available:
            desc = SPECIALIST_DESCRIPTIONS.get(name, "")
            text.append(f"  /invite {name.lower():<11}", style="cyan")
            text.append(f"  {desc}\n", style="dim italic")

    console.print(Panel(text, title="[bold]council[/bold]", border_style="dim"))


def _handle_command(
    cmd: str,
    models: dict[str, str],
    deliberation: Deliberation | None,
    console: Console,
) -> tuple[dict, Deliberation | None, bool]:
    parts = cmd.lower().strip().split(maxsplit=1)
    head = parts[0] if parts else ""
    arg = parts[1] if len(parts) > 1 else ""

    if head in ("exit", "quit", "q"):
        console.print("[dim]MAGI offline.[/dim]")
        return models, deliberation, False

    if head == "help":
        print_help(console)
    elif head == "models":
        print_models(console, models)
    elif head in ("specialists", "council", "roster"):
        _print_council_roster(console, models)
    elif head == "journal":
        entries = journal.load_entries(limit=20)
        render_journal(entries, console)
    elif head == "stats":
        entries = journal.load_entries()
        render_stats(entries, console)
    elif head == "outcome":
        parts_arg = arg.split(maxsplit=1)
        if len(parts_arg) < 2:
            console.print("[red]usage: /outcome <id> <what you did>[/red]  [dim](e.g. /outcome a3f5b9c2 did it, no regrets)[/dim]")
        else:
            id_prefix, outcome_text = parts_arg
            outcome_text = outcome_text[:500]
            if journal.set_user_outcome(id_prefix, outcome_text):
                console.print(f"[dim]outcome recorded for [bold]{id_prefix}[/bold][/dim]")
            else:
                console.print(f"[red]no entry found matching id [bold]{id_prefix}[/bold][/red]")
    elif head == "clear":
        console.clear()
        print_banner(console, models)
    elif head in ("new", "n"):
        if deliberation is not None and deliberation.turn > 0:
            console.print(f"[dim]new deliberation (closed prior thread, {deliberation.turn} turn(s))[/dim]")
        else:
            console.print("[dim]new deliberation[/dim]")
        deliberation = None
    elif head == "invite":
        if not arg:
            console.print("[red]usage: /invite <specialist>[/red]  [dim](e.g. /invite banker)[/dim]")
            console.print(f"  [dim]available: {', '.join(s.lower() for s in SPECIALISTS)}[/dim]")
        else:
            specialist = arg.upper()
            if specialist not in SPECIALISTS:
                console.print(f"[red]unknown specialist: {arg}[/red]")
                console.print(f"  [dim]available: {', '.join(s.lower() for s in SPECIALISTS)}[/dim]")
            elif specialist in models:
                console.print(f"[dim]{specialist} is already in the council[/dim]")
            else:
                models[specialist] = SPECIALIST_DEFAULT_MODELS[specialist]
                if deliberation is not None:
                    deliberation.add_member(specialist)
                desc = SPECIALIST_DESCRIPTIONS.get(specialist, "")
                console.print(f"[bold magenta]{specialist}[/bold magenta] joins the council  [dim]({desc})[/dim]")
    elif head == "dismiss":
        if not arg:
            console.print("[red]usage: /dismiss <specialist>[/red]")
        else:
            specialist = arg.upper()
            if is_core_member(specialist):
                console.print(f"[red]cannot dismiss core MAGI member {specialist}[/red]")
            elif specialist not in models:
                console.print(f"[dim]{specialist} is not in the council[/dim]")
            else:
                models.pop(specialist)
                if deliberation is not None:
                    deliberation.remove_member(specialist)
                console.print(f"[dim]{specialist} leaves the council[/dim]")
    elif head in PERSONAS_LOWER:
        canonical = head.upper()
        if not arg:
            console.print(f"[red]usage: /{head} <model>[/red]  [dim](e.g. /{head} qwen3:8b)[/dim]")
        else:
            models[canonical] = arg
            console.print(f"[dim]{canonical} → [bold]{arg}[/bold][/dim]")
    elif head in SPECIALISTS_LOWER and head in [s.lower() for s in models if not is_core_member(s)]:
        # /banker <model> works only if banker is invited
        canonical = head.upper()
        if not arg:
            console.print(f"[red]usage: /{head} <model>[/red]")
        else:
            models[canonical] = arg
            console.print(f"[dim]{canonical} → [bold]{arg}[/bold][/dim]")
    elif head == "reset":
        models.clear()
        models.update(DEFAULT_MODELS)
        if deliberation is not None:
            for name in list(deliberation.histories):
                if not is_core_member(name):
                    deliberation.remove_member(name)
        console.print("[dim]models reset; specialists dismissed[/dim]")
        print_models(console, models)
    else:
        console.print(f"[red]unknown command: /{head}[/red]  [dim](try /help)[/dim]")

    return models, deliberation, True


PERSONAS_LOWER = {n.lower() for n in PERSONAS}
SPECIALISTS_LOWER = {n.lower() for n in SPECIALISTS}


async def run_repl(initial_models: dict[str, str]) -> None:
    console = Console()
    console.clear()
    journal.cleanup_stale_temps()
    print_banner(console, initial_models)
    models = dict(initial_models)
    try:
        await warm_council(models, console)
    except OllamaUnavailable as e:
        console.print(f"[red bold]{e}[/red bold]")
        console.print("[dim]start Ollama and try again[/dim]")
        return
    deliberation: Deliberation | None = None

    while True:
        prompt = "[bold red]❯❯[/bold red] " if deliberation is not None else "[bold red]❯[/bold red] "
        try:
            line = console.input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]MAGI offline.[/dim]")
            return

        if not line:
            continue

        if line.startswith("/"):
            models, deliberation, cont = _handle_command(line[1:], models, deliberation, console)
            if not cont:
                return
            continue

        if deliberation is None:
            deliberation = Deliberation(list(models.keys()))

        deliberation.add_user_message(line)

        try:
            await run_full_deliberation(deliberation, models, console)
        except KeyboardInterrupt:
            console.print("\n[yellow]deliberation interrupted[/yellow]")

        # If the noise bounce popped the only user message, drop the empty
        # deliberation so the next prompt shows ❯ (fresh thread) not ❯❯ (continue).
        if deliberation is not None and deliberation.turn == 0:
            deliberation = None


async def run_full_deliberation(
    deliberation: Deliberation, models: dict[str, str], console: Console
) -> None:
    """Classify the user's latest question, then route to the right deliberation
    flow. choice → option-tally mode; everything else → ACCEPT/REJECT/CONDITIONAL."""
    sample_history = next(iter(deliberation.histories.values()), [])
    user_msgs = [m["content"] for m in sample_history if m["role"] == "user"]
    if not user_msgs:
        return
    question = user_msgs[-1]

    # A follow-up is evidence for a thread that is already running. Sending it
    # back through intake bounced "i have a tested rollback and the team is on
    # call through the weekend" as noise, which killed the whole point of
    # arguing back. Follow-ups inherit the thread's mode and skip the
    # classifier entirely, which is also a second or two faster.
    is_followup = deliberation.turn > 1 and deliberation.mode is not None
    if is_followup:
        classification = Classification(
            question_class=QuestionClass(deliberation.mode),
            options=list(deliberation.options),
        )
    else:
        classification = await classify_safe(question)

        if classification.question_class == QuestionClass.NOISE:
            # Roll back the polluting user message so the next real question
            # doesn't see "hello" sitting in every persona's history.
            for hist in deliberation.histories.values():
                if hist and hist[-1]["role"] == "user":
                    hist.pop()
            console.print(
                "[dim italic]the council convenes for questions, not greetings — "
                "try \"should I X?\" or \"A or B?\"[/dim italic]"
            )
            return

        deliberation.mode = classification.question_class.value
        deliberation.options = list(classification.options)
        deliberation.frame(classification.decision)
        render_intake(classification.question_class.value, classification.options, console,
                      decision=classification.decision)

    hits = search(question)
    if hits:
        render_memory_hits(hits, console)
        context = build_context(hits)
        if context:
            augmented = context + "\n" + question
            for hist in deliberation.histories.values():
                if hist and hist[-1]["role"] == "user":
                    hist[-1]["content"] = augmented

    if classification.question_class == QuestionClass.CHOICE and len(classification.options) >= 2:
        await _run_choice_flow(question, classification.options, deliberation, models, console)
    elif classification.question_class == QuestionClass.OPEN:
        await _run_recommend_flow(question, deliberation, models, console)
    else:
        await _run_decision_flow(question, deliberation, models, console)

    patterns = detect_patterns(question)
    render_patterns(patterns, console)


async def _run_decision_flow(
    question: str, deliberation: Deliberation, models: dict[str, str], console: Console
) -> None:
    """Drive ACCEPT/REJECT/CONDITIONAL deliberation, rendering each round live."""
    initial_votes: dict = {}
    round_rebuttals: dict[int, dict] = {}
    previous_verdicts: dict[str, Verdict] = {}
    final_outcome = "incomplete"
    final_positions: dict = {}

    vote_statuses = {name: f"voting  [{models[name]}]" for name in models}
    live: Live | None = Live(vote_status_panel(models, vote_statuses, initial_votes), console=console, refresh_per_second=8)
    live.__enter__()

    debate_statuses: dict[str, str] = {}
    debate_round_num = 0
    in_round_one = True

    try:
        async for event in iterative_deliberate(deliberation, models):
            kind = event[0]

            if kind == "round_start":
                round_num = event[1]
                if round_num == 1:
                    continue

                if live is not None:
                    live.__exit__(None, None, None)
                    live = None

                if in_round_one:
                    console.print()
                    render_initial_votes(initial_votes, console)
                    console.print()
                    for name, response in initial_votes.items():
                        if isinstance(response, PersonaResponse):
                            previous_verdicts[name] = response.verdict
                    in_round_one = False
                else:
                    console.print()
                    render_debate_round(debate_round_num, round_rebuttals[debate_round_num], previous_verdicts, console)
                    console.print()
                    for name, rebuttal in round_rebuttals[debate_round_num].items():
                        if isinstance(rebuttal, Rebuttal):
                            previous_verdicts[name] = rebuttal.final_verdict

                debate_round_num = round_num
                round_rebuttals[round_num] = {}
                debate_statuses = {
                    name: f"debating  [{models[name]}]"
                    for name in initial_votes
                    if isinstance(initial_votes[name], PersonaResponse)
                }
                live = Live(
                    debate_status_panel(models, debate_statuses, round_rebuttals[round_num], round_num),
                    console=console,
                    refresh_per_second=8,
                )
                live.__enter__()

            elif kind == "vote":
                _, name, payload = event
                initial_votes[name] = payload
                sound.play("error" if isinstance(payload, Exception) else "report")
                if isinstance(payload, Exception):
                    vote_statuses[name] = f"failed: {type(payload).__name__}"
                else:
                    vote_statuses[name] = f"{payload.verdict.value}  [{models[name]}]"
                if live is not None:
                    live.update(vote_status_panel(models, vote_statuses, initial_votes))

            elif kind == "revote":
                sound.play("revote")
                # This member restated somebody else's argument and was sent
                # back to find the one only their lens produces.
                _, name, payload = event
                initial_votes[name] = payload
                vote_statuses[name] = f"{payload.verdict.value}  ↻ own lens  [{models[name]}]"
                if live is not None:
                    live.update(vote_status_panel(models, vote_statuses, initial_votes))

            elif kind == "rebuttal":
                _, name, payload = event
                sound.play("error" if isinstance(payload, Exception) else "report")
                round_rebuttals[debate_round_num][name] = payload
                if isinstance(payload, Exception):
                    debate_statuses[name] = f"failed: {type(payload).__name__}"
                elif isinstance(payload, Rebuttal):
                    prev = previous_verdicts.get(name)
                    if prev is None:
                        initial = initial_votes.get(name)
                        if isinstance(initial, PersonaResponse):
                            prev = initial.verdict
                    arrow = "→" if prev == payload.final_verdict else "⇒"
                    debate_statuses[name] = f"{arrow} {payload.final_verdict.value}  [{models[name]}]"
                if live is not None:
                    live.update(debate_status_panel(models, debate_statuses, round_rebuttals[debate_round_num], debate_round_num))

            elif kind == "done":
                _, outcome, positions = event
                final_outcome = outcome
                final_positions = positions
    finally:
        if live is not None:
            live.__exit__(None, None, None)
            live = None

    if in_round_one:
        console.print()
        render_initial_votes(initial_votes, console)
    else:
        console.print()
        render_debate_round(debate_round_num, round_rebuttals[debate_round_num], previous_verdicts, console)

    synthesis_text = synthesize(final_positions, outcome=final_outcome)
    render_synthesis(synthesis_text, final_outcome, console)

    rounds_count = max(round_rebuttals.keys()) if round_rebuttals else 1
    final_verdicts = {
        name: r.verdict.value
        for name, r in final_positions.items()
        if isinstance(r, PersonaResponse)
    }
    _save_journal(question, list(final_positions.keys()), rounds_count, final_outcome, synthesis_text, final_verdicts, console)


async def _run_choice_flow(
    question: str,
    options: list[str],
    deliberation: Deliberation,
    models: dict[str, str],
    console: Console,
) -> None:
    """Drive choice deliberation. Same shape as decision flow but with
    ChoiceResponse / ChoiceRebuttal types and option-tally synthesis."""
    initial_votes: dict = {}
    round_rebuttals: dict[int, dict] = {}
    previous_choices: dict[str, str] = {}
    final_outcome = "incomplete"
    final_positions: dict = {}

    vote_statuses = {name: f"picking  [{models[name]}]" for name in models}
    live: Live | None = Live(choice_vote_status_panel(models, vote_statuses, initial_votes), console=console, refresh_per_second=8)
    live.__enter__()

    debate_statuses: dict[str, str] = {}
    debate_round_num = 0
    in_round_one = True

    try:
        async for event in iterative_choose(deliberation, models, options):
            kind = event[0]

            if kind == "round_start":
                round_num = event[1]
                if round_num == 1:
                    continue

                if live is not None:
                    live.__exit__(None, None, None)
                    live = None

                if in_round_one:
                    console.print()
                    render_initial_choices(initial_votes, console)
                    console.print()
                    for name, response in initial_votes.items():
                        if isinstance(response, ChoiceResponse):
                            previous_choices[name] = response.chosen_option
                    in_round_one = False
                else:
                    console.print()
                    render_choice_debate_round(debate_round_num, round_rebuttals[debate_round_num], previous_choices, console)
                    console.print()
                    for name, rebuttal in round_rebuttals[debate_round_num].items():
                        if isinstance(rebuttal, ChoiceRebuttal):
                            previous_choices[name] = rebuttal.final_choice

                debate_round_num = round_num
                round_rebuttals[round_num] = {}
                debate_statuses = {
                    name: f"debating  [{models[name]}]"
                    for name in initial_votes
                    if isinstance(initial_votes[name], ChoiceResponse)
                }
                live = Live(
                    choice_debate_status_panel(models, debate_statuses, round_rebuttals[round_num], round_num),
                    console=console,
                    refresh_per_second=8,
                )
                live.__enter__()

            elif kind == "vote":
                _, name, payload = event
                initial_votes[name] = payload
                sound.play("error" if isinstance(payload, Exception) else "report")
                if isinstance(payload, Exception):
                    vote_statuses[name] = f"failed: {type(payload).__name__}"
                else:
                    vote_statuses[name] = f"{payload.chosen_option}  [{models[name]}]"
                if live is not None:
                    live.update(choice_vote_status_panel(models, vote_statuses, initial_votes))

            elif kind == "revote":
                sound.play("revote")
                # Sent back for restating another member's reasoning.
                _, name, payload = event
                initial_votes[name] = payload
                vote_statuses[name] = f"{payload.chosen_option}  ↻ own lens  [{models[name]}]"
                if live is not None:
                    live.update(choice_vote_status_panel(models, vote_statuses, initial_votes))

            elif kind == "rebuttal":
                _, name, payload = event
                sound.play("error" if isinstance(payload, Exception) else "report")
                round_rebuttals[debate_round_num][name] = payload
                if isinstance(payload, Exception):
                    debate_statuses[name] = f"failed: {type(payload).__name__}"
                elif isinstance(payload, ChoiceRebuttal):
                    prev = previous_choices.get(name)
                    if prev is None:
                        initial = initial_votes.get(name)
                        if isinstance(initial, ChoiceResponse):
                            prev = initial.chosen_option
                    arrow = "→" if prev == payload.final_choice else "⇒"
                    debate_statuses[name] = f"{arrow} {payload.final_choice}  [{models[name]}]"
                if live is not None:
                    live.update(choice_debate_status_panel(models, debate_statuses, round_rebuttals[debate_round_num], debate_round_num))

            elif kind == "done":
                _, outcome, positions = event
                final_outcome = outcome
                final_positions = positions
    finally:
        if live is not None:
            live.__exit__(None, None, None)
            live = None

    if in_round_one:
        console.print()
        render_initial_choices(initial_votes, console)
    else:
        console.print()
        render_choice_debate_round(debate_round_num, round_rebuttals[debate_round_num], previous_choices, console)

    synthesis_text = synthesize_choice(final_positions, final_outcome, options)
    render_synthesis(synthesis_text, final_outcome, console)

    rounds_count = max(round_rebuttals.keys()) if round_rebuttals else 1
    final_choices = {
        name: r.chosen_option
        for name, r in final_positions.items()
        if isinstance(r, ChoiceResponse)
    }
    _save_journal(question, list(final_positions.keys()), rounds_count, final_outcome, synthesis_text, final_choices, console)


async def _run_recommend_flow(
    question: str,
    deliberation: Deliberation,
    models: dict[str, str],
    console: Console,
) -> None:
    """Drive recommend deliberation. Each persona returns ONE concrete pick;
    no verdict aggregation, no convergence pressure. Output is N distinct picks."""
    initial_votes: dict = {}
    round_rebuttals: dict[int, dict] = {}
    previous_recs: dict[str, str] = {}
    final_outcome = "picks"
    final_positions: dict = {}

    vote_statuses = {name: f"recommending  [{models[name]}]" for name in models}
    live: Live | None = Live(recommend_vote_status_panel(models, vote_statuses, initial_votes), console=console, refresh_per_second=8)
    live.__enter__()

    debate_statuses: dict[str, str] = {}
    debate_round_num = 0
    in_round_one = True

    try:
        async for event in iterative_recommend(deliberation, models):
            kind = event[0]

            if kind == "round_start":
                round_num = event[1]
                if round_num == 1:
                    continue

                if live is not None:
                    live.__exit__(None, None, None)
                    live = None

                if in_round_one:
                    console.print()
                    render_initial_recommendations(initial_votes, console)
                    console.print()
                    for name, response in initial_votes.items():
                        if isinstance(response, RecommendResponse):
                            previous_recs[name] = response.recommendation
                    in_round_one = False
                else:
                    console.print()
                    render_recommend_debate_round(debate_round_num, round_rebuttals[debate_round_num], previous_recs, console)
                    console.print()
                    for name, rebuttal in round_rebuttals[debate_round_num].items():
                        if isinstance(rebuttal, RecommendRebuttal):
                            previous_recs[name] = rebuttal.final_recommendation

                debate_round_num = round_num
                round_rebuttals[round_num] = {}
                debate_statuses = {
                    name: f"refining  [{models[name]}]"
                    for name in initial_votes
                    if isinstance(initial_votes[name], RecommendResponse)
                }
                live = Live(
                    recommend_debate_status_panel(models, debate_statuses, round_rebuttals[round_num], round_num),
                    console=console,
                    refresh_per_second=8,
                )
                live.__enter__()

            elif kind == "vote":
                _, name, payload = event
                initial_votes[name] = payload
                sound.play("error" if isinstance(payload, Exception) else "report")
                if isinstance(payload, Exception):
                    vote_statuses[name] = f"failed: {type(payload).__name__}"
                else:
                    short = payload.recommendation if len(payload.recommendation) <= 60 else payload.recommendation[:57] + "..."
                    vote_statuses[name] = f"{short}  [{models[name]}]"
                if live is not None:
                    live.update(recommend_vote_status_panel(models, vote_statuses, initial_votes))

            elif kind == "rebuttal":
                _, name, payload = event
                sound.play("error" if isinstance(payload, Exception) else "report")
                round_rebuttals[debate_round_num][name] = payload
                if isinstance(payload, Exception):
                    debate_statuses[name] = f"failed: {type(payload).__name__}"
                elif isinstance(payload, RecommendRebuttal):
                    prev = previous_recs.get(name, "")
                    arrow = "→" if prev.lower().strip() == payload.final_recommendation.lower().strip() else "⇒"
                    short = payload.final_recommendation if len(payload.final_recommendation) <= 50 else payload.final_recommendation[:47] + "..."
                    debate_statuses[name] = f"{arrow} {short}  [{models[name]}]"
                if live is not None:
                    live.update(recommend_debate_status_panel(models, debate_statuses, round_rebuttals[debate_round_num], debate_round_num))

            elif kind == "done":
                _, outcome, positions = event
                final_outcome = outcome
                final_positions = positions
    finally:
        if live is not None:
            live.__exit__(None, None, None)
            live = None

    if in_round_one:
        console.print()
        render_initial_recommendations(initial_votes, console)
    else:
        console.print()
        render_recommend_debate_round(debate_round_num, round_rebuttals[debate_round_num], previous_recs, console)

    synthesis_text = synthesize_recommend(final_positions)
    render_synthesis(synthesis_text, "deadlock" if "DISTINCT" in synthesis_text or "PARTIAL" in synthesis_text else "consensus", console)

    rounds_count = max(round_rebuttals.keys()) if round_rebuttals else 1
    final_recs = {
        name: r.recommendation
        for name, r in final_positions.items()
        if isinstance(r, RecommendResponse)
    }
    _save_journal(question, list(final_positions.keys()), rounds_count, final_outcome, synthesis_text, final_recs, console)


def _save_journal(
    question: str,
    members: list[str],
    rounds: int,
    outcome: str,
    synthesis: str,
    final_verdicts: dict[str, str],
    console: Console,
) -> None:
    if not final_verdicts:
        return
    try:
        entry_id = journal.save_entry(
            question=question,
            members=members,
            rounds=rounds,
            outcome=outcome,
            synthesis=synthesis,
            final_verdicts=final_verdicts,
        )
        console.print(f"[dim]logged as {entry_id}  ·  /journal to review[/dim]")
    except Exception as e:
        console.print(f"[dim red]journal write failed: {e}[/dim red]")


async def _run_quiet_deliberation(
    deliberation: Deliberation, models: dict[str, str]
) -> str:
    """Run a full deliberation silently, return only the synthesis string."""
    sample_history = next(iter(deliberation.histories.values()), [])
    user_msgs = [m["content"] for m in sample_history if m["role"] == "user"]
    if not user_msgs:
        return "ERROR: no question"
    question = user_msgs[-1]

    classification = await classify_safe(question)

    if classification.question_class == QuestionClass.NOISE:
        return "NOISE: not a question"

    if classification.question_class == QuestionClass.CHOICE and len(classification.options) >= 2:
        final_positions: dict = {}
        final_outcome = "incomplete"
        async for event in iterative_choose(deliberation, models, classification.options):
            if event[0] == "done":
                _, final_outcome, final_positions = event
        return synthesize_choice(final_positions, final_outcome, classification.options)

    if classification.question_class == QuestionClass.OPEN:
        final_positions = {}
        async for event in iterative_recommend(deliberation, models):
            if event[0] == "done":
                _, _, final_positions = event
        return synthesize_recommend(final_positions)

    final_positions = {}
    final_outcome = "incomplete"
    async for event in iterative_deliberate(deliberation, models):
        if event[0] == "done":
            _, final_outcome, final_positions = event
    return synthesize(final_positions, outcome=final_outcome)


async def run_stats() -> None:
    console = Console()
    entries = journal.load_entries()
    render_stats(entries, console)


async def run_oneshot(question: str, models: dict[str, str], quiet: bool = False) -> None:
    if quiet:
        from io import StringIO
        buf_console = Console(file=StringIO(), force_terminal=False)
        try:
            await warm_council(models, buf_console)
        except OllamaUnavailable as e:
            import sys
            print(str(e), file=sys.stderr)
            sys.exit(2)
        deliberation = Deliberation(list(models.keys()))
        deliberation.add_user_message(question)
        synthesis_text = await _run_quiet_deliberation(deliberation, models)
        print(synthesis_text)
        return

    console = Console()
    try:
        await warm_council(models, console)
    except OllamaUnavailable as e:
        console.print(f"[red bold]{e}[/red bold]")
        return
    deliberation = Deliberation(list(models.keys()))
    deliberation.add_user_message(question)
    await run_full_deliberation(deliberation, models, console)
