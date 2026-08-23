import asyncio
from typing import AsyncIterator

import httpx

from magi.config import OLLAMA_HOST
from magi.core import KEEP_ALIVE
from magi.providers import NUM_CTX, is_local

# Cold load of a 7B model from disk can take 30-60s on memory-pressured Macs.
WARMUP_TIMEOUT = 180.0


def warmup_body(model: str) -> dict:
    """The load request. `options` must match what deliberation later asks
    for: warm a model at a different context size and Ollama unloads and
    reloads it on the first real call, so warmup pays the load cost twice
    instead of saving it."""
    return {
        "model": model,
        "prompt": "",
        "keep_alive": KEEP_ALIVE,
        "stream": False,
        "options": {"num_ctx": NUM_CTX},
    }


async def warmup_models(
    models: dict[str, str],
) -> AsyncIterator[tuple[str, str, Exception | None]]:
    """Pre-load models into Ollama memory in parallel.
    Yields (name, model_id, error_or_None) as each finishes.
    Cloud models (provider/model specs) need no warmup and complete instantly."""
    local = {n: m for n, m in models.items() if is_local(m)}
    for name, model in models.items():
        if name not in local:
            yield name, model, None

    if not local:
        return

    async with httpx.AsyncClient(timeout=WARMUP_TIMEOUT) as client:
        async def warm_one(name: str, model: str):
            try:
                r = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json=warmup_body(model),
                )
                r.raise_for_status()
                return name, model, None
            except Exception as e:
                return name, model, e

        tasks = [asyncio.create_task(warm_one(n, m)) for n, m in local.items()]
        try:
            for coro in asyncio.as_completed(tasks):
                yield await coro
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
