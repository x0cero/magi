"""magi doctor: pre-flight check for Ollama, models, and config."""


import httpx
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from magi.config import CONFIG_PATH, OLLAMA_HOST, load_config
from magi.core import DEFAULT_MODELS
from magi.providers import _KEY_ENV_VARS, get_api_key, is_local, parse_model_spec

REQUIRED_MODELS = list(DEFAULT_MODELS.values())


def _effective_models() -> dict[str, str]:
    """Core roster after config.toml overrides."""
    models = dict(DEFAULT_MODELS)
    cfg_models = load_config().get("models", {})
    for name in ("melchior", "balthasar", "casper"):
        if cfg_models.get(name):
            models[name.upper()] = cfg_models[name]
    return models


async def _check_ollama() -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/version")
            r.raise_for_status()
            version = r.json().get("version", "unknown")
            return True, version
    except httpx.ConnectError:
        return False, "not running"
    except Exception as e:
        return False, str(e)


async def _list_pulled_models() -> dict[str, dict]:
    """Returns {model_name: {size, modified_at, ...}} for all pulled models."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
            return {m["name"]: m for m in models}
    except Exception:
        return {}


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.0f} MB"
    return f"{size_bytes} B"


async def run_doctor() -> int:
    """Run all checks, print results. Returns 0 if healthy, 1 if issues."""
    console = Console()
    issues = 0

    effective = _effective_models()
    local_models = sorted({m for m in effective.values() if is_local(m)})
    cloud_models = sorted({m for m in effective.values() if not is_local(m)})

    ok, version = await _check_ollama()
    text = Text()
    if ok:
        text.append("  OK  ", style="bold green")
        text.append(f"Ollama {version} at {OLLAMA_HOST}\n")
    elif not local_models:
        text.append("  --  ", style="dim")
        text.append(f"Ollama not reachable at {OLLAMA_HOST} (not needed — all council models are cloud)\n", style="dim")
    else:
        text.append("  !!  ", style="bold red")
        text.append(f"Ollama not reachable at {OLLAMA_HOST}\n", style="red")
        text.append("       install: https://ollama.com\n", style="dim")
        text.append("       start:   ollama serve\n", style="dim")
        issues += 1

    console.print(Panel(text, title="[bold]Ollama[/bold]", border_style="dim"))

    if cloud_models:
        prov_text = Text()
        for spec in cloud_models:
            provider, _ = parse_model_spec(spec)
            if get_api_key(provider):
                prov_text.append("  OK  ", style="bold green")
                prov_text.append(f"{spec:<40}  key found\n")
            else:
                prov_text.append("  !!  ", style="bold red")
                prov_text.append(f"{spec:<40}  ", style="red")
                prov_text.append(f"missing key — set {_KEY_ENV_VARS[provider]}\n", style="dim")
                issues += 1
        console.print(Panel(prov_text, title="[bold]Cloud Providers[/bold]", border_style="dim"))

    if not ok:
        if issues:
            console.print(f"\n[red bold]{issues} issue(s) found[/red bold]")
            return 1
        console.print("\n[green bold]all checks passed[/green bold]")
        return 0

    pulled = await _list_pulled_models()
    model_text = Text()
    total_size = 0

    unique_models = local_models
    for model in unique_models:
        if model in pulled:
            size = pulled[model].get("size", 0)
            total_size += size
            model_text.append("  OK  ", style="bold green")
            model_text.append(f"{model:<20}  {_format_size(size)}\n")
        else:
            found = False
            for pulled_name in pulled:
                base = pulled_name.split(":")[0]
                model_base = model.split(":")[0]
                if base == model_base:
                    size = pulled[pulled_name].get("size", 0)
                    total_size += size
                    model_text.append("  OK  ", style="bold green")
                    model_text.append(f"{model:<20}  {_format_size(size)}  (matched as {pulled_name})\n")
                    found = True
                    break
            if not found:
                model_text.append("  !!  ", style="bold red")
                model_text.append(f"{model:<20}  ", style="red")
                model_text.append(f"not pulled — run: ollama pull {model}\n", style="dim")
                issues += 1

    if total_size > 0:
        model_text.append(f"\n  total footprint: {_format_size(total_size)}\n", style="dim")

    if unique_models:
        console.print(Panel(model_text, title="[bold]Required Models[/bold]", border_style="dim"))

    cfg_text = Text()
    if CONFIG_PATH.exists():
        cfg = load_config()
        cfg_text.append("  OK  ", style="bold green")
        cfg_text.append(f"{CONFIG_PATH}\n")
        if cfg.get("models"):
            for k, v in cfg["models"].items():
                cfg_text.append(f"       {k} = {v}\n", style="dim")
        if cfg.get("specialists", {}).get("invite"):
            cfg_text.append(f"       auto-invite: {', '.join(cfg['specialists']['invite'])}\n", style="dim")
    else:
        cfg_text.append("  --  ", style="dim")
        cfg_text.append(f"no config file (optional: {CONFIG_PATH})\n", style="dim")

    console.print(Panel(cfg_text, title="[bold]Config[/bold]", border_style="dim"))

    if issues:
        console.print(f"\n[red bold]{issues} issue(s) found[/red bold]")
    else:
        console.print("\n[green bold]all checks passed[/green bold]")

    return 1 if issues else 0
