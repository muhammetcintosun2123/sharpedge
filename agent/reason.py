"""
agent/reason.py — LLM explanation layer (sits ON TOP of the deterministic core).

The detector decides WHAT is a sharp move (deterministic, defensible). The LLM only
turns that structured signal into a crisp, human-readable read for a trader — it
NEVER changes the signal. Judges reward "clean, deterministic logic"; this keeps the
decision math untouched and uses the LLM purely for the last-mile narrative + tagging.

Falls back to a deterministic template if no LLM key is configured, so the agent
always runs (production-ready / no hard dependency on an external API key).
"""
from __future__ import annotations

import asyncio
from typing import Optional

from .detector import Signal
from . import llm

_SYSTEM = (
    "You are a sharp-betting-market analyst. You get a STRUCTURED signal that a "
    "deterministic detector already classified as sharp money. In ONE tight sentence "
    "(<=25 words), tell a trader what it means and a plausible read — never hedge, "
    "never invent facts not in the data. No preamble."
)


def _template(sig: Signal) -> str:
    dirn = "money IN (shortening)" if sig.delta_p > 0 else "money OUT (drifting)"
    return (f"{sig.kind}: sharp {dirn} on '{sig.selection}', {abs(sig.delta_p)*100:.1f}pp "
            f"in one tick ({abs(sig.z):.1f}σ) — {sig.prob_before:.0%}→{sig.prob_after:.0%}. "
            f"Fast one-way consensus shift = likely informed money.")


async def explain_async(sig: Signal) -> str:
    if not llm.available():
        return _template(sig)
    # Direction is decided deterministically here — the LLM must NOT recompute it.
    flow = "INTO" if sig.delta_p > 0 else "OUT OF"
    rating = "MORE" if sig.delta_p > 0 else "LESS"
    prompt = (f"Match: {sig.match}\nSelection: {sig.selection}\n"
              f"FACTS (state these exactly, do not reinterpret): sharp money flowed {flow} "
              f"'{sig.selection}'; the market now rates it {rating} likely. Fair prob "
              f"{sig.prob_before:.3f} -> {sig.prob_after:.3f} (Δ {sig.delta_p:+.3f}, "
              f"{abs(sig.z):.1f} sigma), decimal odds now {sig.odds_after}, class {sig.kind}.\n"
              f"Write one sentence (<=25 words) for a trader. Keep the direction exactly as stated.")
    out = await llm.chat(prompt, system=_SYSTEM, temperature=0.3, max_tokens=80)
    return (out or _template(sig)).strip()


def explain(sig: Signal) -> str:
    try:
        return asyncio.run(explain_async(sig))
    except RuntimeError:
        return _template(sig)
