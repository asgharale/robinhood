"""
Rough token accounting for trimming conversation history before an LLM call.

This is intentionally not a real tokenizer. Pulling in tiktoken or a
model-specific tokenizer isn't worth it here because the providers behind
the router use different tokenizers anyway (Llama, Gemini, Qwen, ...), so
no single exact count would be correct for all of them. A conservative
character-based estimate is enough to keep requests under HISTORY_TOKEN_BUDGET
with headroom to spare.
"""

# ~4 characters per token is a common rule of thumb for English; for mixed
# Persian/English content we bias slightly higher (fewer chars/token) to stay
# conservative rather than risk overflowing a provider's context window.
CHARS_PER_TOKEN = 4.5


def estimate_tokens(text: str) -> int:
    """Cheap upper-bound estimate of token count for a piece of text."""
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def trim_history(rows: list[dict], budget: int) -> list[dict]:
    """
    rows: [{"role": ..., "content": ...}, ...] oldest-first (already reversed
    by the caller). Returns the most recent messages that fit within `budget`
    tokens, oldest-first, so the LLM sees them in chronological order.

    If budget is already <= 0 (a very long incoming question ate the whole
    window), history is dropped entirely rather than raising - the current
    question always takes priority over past turns.
    """
    if budget <= 0 or not rows:
        return []

    kept = []
    used = 0
    # Walk from the newest message backwards, keeping whole messages until
    # the budget would be exceeded.
    for row in reversed(rows):
        cost = estimate_tokens(row["content"]) + 4  # +4 for role/format overhead
        if used + cost > budget:
            break
        kept.append({"role": row["role"], "content": row["content"]})
        used += cost

    kept.reverse()
    return kept