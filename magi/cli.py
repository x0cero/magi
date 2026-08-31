import asyncio
import sys

import click

from magi import __version__
from magi.config import apply_config, init_config
from magi.core import DEFAULT_MODELS
from magi.personas import SPECIALIST_DEFAULT_MODELS, SPECIALISTS


@click.command()
@click.version_option(__version__, "-V", "--version", prog_name="magi")
@click.argument("question", nargs=-1, required=False)
@click.option("--melchior", default=None, help=f"Override Melchior's model (default: {DEFAULT_MODELS['MELCHIOR']})")
@click.option("--balthasar", default=None, help=f"Override Balthasar's model (default: {DEFAULT_MODELS['BALTHASAR']})")
@click.option("--casper", default=None, help=f"Override Casper's model (default: {DEFAULT_MODELS['CASPER']})")
@click.option("--invite", multiple=True, help=f"Invite a specialist (one of: {', '.join(s.lower() for s in SPECIALISTS)}). Repeatable.")
@click.option("--quiet", "-q", is_flag=True, help="Output only the final verdict line (for scripting).")
@click.option("--init-config", "do_init_config", is_flag=True, help="Write example config to ~/.config/magi/config.toml and exit.")
def cli(
    question: tuple[str, ...],
    melchior: str | None,
    balthasar: str | None,
    casper: str | None,
    invite: tuple[str, ...],
    quiet: bool,
    do_init_config: bool,
) -> None:
    """MAGI: three-agent decision council inspired by Evangelion.

    Three open-source models served via Ollama deliberate on a question.
    They argue across multiple rounds until consensus or deadlock.

    \b
    Examples:
        magi                                    open the REPL
        magi "should I take the job offer?"     one-shot
        magi doctor                             check Ollama + models
        magi stats                              journal analytics
        echo "should I?" | magi -q              pipe + quiet mode
        magi --invite banker "should I move?"   invite a specialist
    """
    if do_init_config:
        from magi.config import config_path_display
        created = init_config()
        if created:
            click.echo(f"config written to {config_path_display()}")
        else:
            click.echo(f"config already exists at {config_path_display()}")
        return

    if question and question[0].lower() == "doctor":
        from magi.doctor import run_doctor
        sys.exit(asyncio.run(run_doctor()))

    if question and question[0].lower() == "stats":
        from magi.repl import run_stats
        asyncio.run(run_stats())
        return

    models = dict(DEFAULT_MODELS)
    models, auto_invited = apply_config(
        models,
        {"melchior": melchior, "balthasar": balthasar, "casper": casper},
    )

    for spec in invite:
        canonical = spec.upper()
        if canonical not in SPECIALISTS:
            click.echo(f"warning: unknown specialist {spec!r}; available: {', '.join(s.lower() for s in SPECIALISTS)}", err=True)
            continue
        if canonical not in models:
            models[canonical] = SPECIALIST_DEFAULT_MODELS[canonical]

    from magi.repl import run_oneshot, run_repl

    pipe_input = None
    if not sys.stdin.isatty():
        from magi.core import MAX_INPUT_CHARS
        pipe_input = sys.stdin.read(MAX_INPUT_CHARS + 1).strip()

    if pipe_input:
        asyncio.run(run_oneshot(pipe_input, models, quiet=quiet))
    elif question:
        asyncio.run(run_oneshot(" ".join(question), models, quiet=quiet))
    else:
        if quiet:
            click.echo("--quiet is only for one-shot mode (pass a question or pipe stdin)", err=True)
            sys.exit(1)
        asyncio.run(run_repl(models))
