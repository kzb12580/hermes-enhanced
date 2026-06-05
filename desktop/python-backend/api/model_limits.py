"""Model-specific tool argument size limits and reasoning model detection.

When a tool call argument exceeds the model's limit, the backend
splits the content into chunks and guides the model to send them
sequentially. This prevents output truncation caused by models
with lower output token limits.

Reasoning models (DeepSeek, MIMO, Qwen, Claude, Gemini) require
reasoning_content/thinking_blocks to be passed back in multi-turn
tool call conversations. Failure to do so causes 400 errors or
quality degradation.
"""

# Per-model limits (characters). Keys are matched case-insensitively
# against model name using `in` operator. First match wins.
MODEL_LIMITS: list[tuple[str, int]] = [
    ("mimo",      3000),   # MIMO truncates aggressively
    ("deepseek",  8000),
    ("qwen",      8000),
    ("gpt-4",    30000),
    ("gpt-3.5",   4000),
    ("claude",   50000),
    ("gemini",   30000),
]

DEFAULT_LIMIT = 5000  # Fallback for unknown models

# Timeout for incomplete chunk sets (seconds)
CHUNK_TIMEOUT = 30 * 60  # 30 minutes

# ─── Reasoning Model Detection ──────────────────────────────────────────
# Models that return reasoning_content in streaming and REQUIRE it to be
# passed back in multi-turn tool call conversations.
#
# "native" = uses `reasoning_content` field (DeepSeek, MIMO, Qwen)
# "thinking_blocks" = uses `thinking_blocks` with signatures (Claude)
# "thought_signatures" = uses thought signatures (Gemini)
# None = no reasoning passback needed (OpenAI, generic)

REASONING_MODELS: list[tuple[str, str]] = [
    ("mimo",       "native"),            # Xiaomi MiMo — reasoning_content
    ("deepseek",   "native"),            # DeepSeek — reasoning_content
    ("qwen",       "native"),            # Alibaba Qwen — reasoning_content
    ("claude",     "thinking_blocks"),   # Anthropic Claude — thinking_blocks + signature
    ("gemini",     "thought_signatures"), # Google Gemini — thought signatures
]


def get_max_tool_arg_chars(model: str | None) -> int:
    """Get max tool argument characters for a model."""
    if not model:
        return DEFAULT_LIMIT
    model_lower = model.lower()
    for pattern, limit in MODEL_LIMITS:
        if pattern in model_lower:
            return limit
    return DEFAULT_LIMIT


def get_chunk_size(model: str | None) -> int:
    """Get chunk size for splitting content. Slightly below limit for safety margin."""
    limit = get_max_tool_arg_chars(model)
    # Leave room for JSON overhead (path, chunk_index, total_chunks keys)
    return max(limit - 500, 1000)


def get_reasoning_type(model: str | None) -> str | None:
    """Get the reasoning content type for a model.
    
    Returns:
        "native" — model uses reasoning_content field (DeepSeek, MIMO, Qwen)
        "thinking_blocks" — model uses thinking_blocks with signatures (Claude)
        "thought_signatures" — model uses thought signatures (Gemini)
        None — model does not require reasoning passback
    """
    if not model:
        return None
    model_lower = model.lower()
    for pattern, rtype in REASONING_MODELS:
        if pattern in model_lower:
            return rtype
    return None


def is_reasoning_model(model: str | None) -> bool:
    """Check if a model requires reasoning content passback."""
    return get_reasoning_type(model) is not None
