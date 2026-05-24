# Hermes Agent — Current Architecture Summary

## Overview

Hermes Agent is a synchronous, tool-calling AI agent that loops through API calls until the model produces a final response or hits a budget limit. The architecture is modular but monolithic — the agent loop, tool execution, context management, and retry/fallback logic are all interleaved in a single function that spans ~4,000 lines.

---

## 1. Agent Loop Flow

### Entry Points
- `AIAgent.run_conversation(user_message, ...)` → forwarder to `agent.conversation_loop.run_conversation()`
- `AIAgent.chat(message)` → calls `run_conversation()` and returns `result["final_response"]`

### Main Loop Structure (`agent/conversation_loop.py`)

```
run_conversation()
  ├── Pre-loop setup (~400 lines)
  │   ├── Sanitize user input (surrogates, encoding)
  │   ├── Build/restore system prompt (cached per session for prefix caching)
  │   ├── Hydrate todo store + nudge counters from conversation history
  │   ├── Preflight context compression (if history > threshold)
  │   ├── Plugin hooks: pre_llm_call
  │   └── Memory manager: prefetch_all()
  │
  └── Main while loop: while (api_call_count < max_iterations AND budget.remaining > 0) OR grace_call
      ├── Interrupt check
      ├── Budget consume check
      ├── Build api_messages (copy of messages + ephemeral injections)
      │   ├── Inject memory context + plugin context into user message
      │   ├── Copy reasoning_content for multi-turn
      │   ├── Apply Anthropic cache_control markers
      │   ├── Sanitize tool_calls for strict APIs
      │   └── Drop thinking-only turns, merge adjacent user messages
      ├── API call (with retry loop inside)
      │   ├── Build api_kwargs
      │   ├── Streaming preferred (health checking), fallback to non-streaming
      │   ├── Response validation + normalization (per api_mode)
      │   └── Error handling → retry with backoff OR fallback model
      │
      ├── If tool_calls present:
      │   ├── Validate tool names (auto-repair, reject invalid)
      │   ├── Validate JSON args (repair, reject truncated)
      │   ├── Cap delegate_task calls, deduplicate
      │   ├── Append assistant message to messages
      │   ├── _execute_tool_calls() → sequential or concurrent
      │   ├── Check compression (should_compress after tool results)
      │   └── continue (loop back for next API call)
      │
      └── If no tool_calls → final_response, exit loop
```

### Key Design Characteristics
- **Synchronous**: The entire loop is blocking/synchronous. Async tool handlers are bridged via `_run_async()` which spins up event loops in threads.
- **Single-threaded main loop**: API calls and sequential tool execution happen on the calling thread. Only concurrent tool execution uses a ThreadPoolExecutor.
- **Grace call**: One extra iteration allowed after budget exhaustion to let the model produce a final response.
- **Retry layer**: Each API call has its own retry loop with jittered exponential backoff (5s base, 120s cap), max retries configurable.

---

## 2. Tool Execution Model

### Dispatch Decision (`_execute_tool_calls`)
```
_execute_tool_calls()
  ├── if NOT _should_parallelize_tool_batch(tool_calls):
  │     → _execute_tool_calls_sequential()
  └── else:
        → _execute_tool_calls_concurrent()
```

### Sequential Execution (`agent/tool_executor.py`)
- Iterates over tool calls one-by-one in order
- Each tool: parse args → check plugins → check guardrails → dispatch → append result
- Special routing for "agent loop tools" (todo, memory, session_search, delegate_task) — handled inline
- All other tools → `handle_function_call()` → `registry.dispatch()`
- Interrupt checked before each tool call
- `tool_delay` between calls (configurable, default 1.0s)

### Concurrent Execution (`agent/tool_executor.py`)
- Uses `concurrent.futures.ThreadPoolExecutor(max_workers=min(N, 8))`
- Propagates ContextVars (approval callbacks, etc.) to worker threads
- Results collected in original order
- Worker threads register their TID for interrupt fan-out
- Periodic heartbeat (every 30s) during wait

### Parallelization Decision (`agent/tool_dispatch_helpers.py`)
- Read-only tools (`read_file`, `search_files`) are always parallel-safe
- Destructive tools (`write_file`, `patch`, `terminal`) only parallelized when paths don't overlap
- Some tools are never parallelizable (`delegate_task`, browser tools)
- `_NEVER_PARALLEL_TOOLS`, `_PARALLEL_SAFE_TOOLS`, `_PATH_SCOPED_TOOLS` sets

### Tool Registry (`tools/registry.py`)
- **Singleton** `ToolRegistry` instance
- Each tool file calls `registry.register()` at import time (self-registration)
- `discover_builtin_tools()` imports all `tools/*.py` files that contain `registry.register()` calls
- `ToolEntry` stores: name, toolset, schema, handler, check_fn, is_async, emoji, max_result_size
- `check_fn` results are TTL-cached (30s) to avoid re-probing external state
- Thread-safe with `_lock` and `_generation` counter for cache invalidation

### Dispatch Chain
```
model_tools.handle_function_call()
  ├── coerce_tool_args() — type coercion ("42" → 42)
  ├── Block check: _AGENT_LOOP_TOOLS (todo, memory, session_search, delegate_task) → return error stub
  ├── Plugin hooks: pre_tool_call (block directive check)
  ├── ACP edit approval check
  ├── registry.dispatch(name, args, task_id=..., ...)
  │   ├── entry.is_async → _run_async(entry.handler(args, **kwargs))
  │   └── entry.handler(args, **kwargs)
  ├── Plugin hooks: post_tool_call (observational)
  └── Plugin hooks: transform_tool_result (can rewrite result)
```

### Async Bridging
- `_run_async(coro)` handles sync→async conversion
- Main thread: persistent event loop (`_get_tool_loop()`)
- Worker threads: per-thread persistent loop (`_get_worker_loop()`)
- Already in async context (gateway): disposable thread with own loop
- 300s timeout on worker thread execution

---

## 3. Message/Context Management

### Message Format
- Standard OpenAI format: `{"role": "system/user/assistant/tool", "content": ..., "tool_calls": ...}`
- Assistant messages have optional `reasoning` field for trajectory storage
- Tool messages include `tool_call_id` for pairing

### Message List Lifecycle
1. `messages = list(conversation_history)` — copy to avoid mutation
2. User message appended
3. **Main loop**: messages accumulate (assistant + tool results)
4. API call uses `api_messages` — a **copy** of messages with ephemeral injections (memory, plugin context, reasoning_content, cache control markers)
5. Original `messages` is the canonical store; `api_messages` is rebuilt each iteration

### System Prompt
- Built once per session via `_build_system_prompt()`
- Cached on `agent._cached_system_prompt`
- Persisted to session DB for prefix-cache reuse (gateway creates fresh AIAgent per turn)
- Never modified during the session (except after compression)
- Ephemeral system prompt appended at API-call time only

### Ephemeral Injections (API-call-time only, not persisted)
- Memory provider prefetch results → injected into user message
- Plugin `pre_llm_call` context → injected into user message
- Prefill messages (few-shot priming) → inserted after system prompt

---

## 4. Compression Approach

### ContextCompressor (`agent/context_compressor.py`)

**Algorithm** (5 phases):
1. **Prune old tool results** — cheap, no LLM call. Replaces large tool outputs with summaries or `[Old tool output cleared to save context space]`
2. **Protect head** — system prompt + first exchange (configurable `protect_first_n`)
3. **Protect tail** — most recent ~20K tokens (token-budget based, not fixed count)
4. **Summarize middle** — uses auxiliary model (cheap/fast) with structured LLM prompt
5. **Iterative updates** — on re-compression, updates the previous summary rather than starting fresh

**Trigger Points**:
- **Preflight**: Before entering main loop, if loaded history exceeds threshold
- **Post-tool**: After tool execution, if `should_compress(real_tokens)` returns True
- **During API retry**: If context limit error from provider, compress and retry

**Key Configuration**:
- `threshold_percent`: % of context_length to trigger compression (default varies)
- `context_length`: Model's context window (auto-detected or configured)
- `tail_token_budget`: ~20K tokens of recent context to protect
- `max_summary_tokens`: Capped at min(5% of context, 12K tokens)
- `SUMMARY_RATIO`: 20% of compressed content allocated for summary
- `abort_on_summary_failure`: Whether to abort compression if LLM summarization fails

**Tool Result Pruning**:
- `_prune_old_tool_results()` — replaces large tool outputs with informative 1-line summaries
- `_summarize_tool_result()` — generates summaries like `[terminal] ran 'npm test' -> exit 0, 47 lines output`
- Image parts in old messages replaced with `[screenshot removed to save context]`

**Summary Format**:
- Structured with `## Active Task`, `## Resolved Questions`, `## Pending` sections
- `SUMMARY_PREFIX` marker warns the model this is reference-only, not active instructions
- Summary merged into tail message to avoid breaking role alternation when needed

---

## 5. Budget/Iteration Tracking

### IterationBudget (`agent/iteration_budget.py`)
- Thread-safe consume/refund counter
- Each AIAgent gets its own budget (parent and subagents are independent)
- `max_iterations` default: 90 (parent), 50 (subagent via delegation config)
- `consume()` → returns False when exhausted
- `refund()` → gives back one iteration (for execute_code turns)
- Grace call: one extra iteration after exhaustion

### Session-Level Tracking
- `session_prompt_tokens`, `session_completion_tokens`, `session_total_tokens`
- `session_api_calls`, `session_estimated_cost_usd`
- `session_cache_read_tokens`, `session_cache_write_tokens`, `session_reasoning_tokens`
- Persisted to session DB for `/insights`

### Per-Turn Budget Enforcement
- `enforce_turn_budget()` in `tools/tool_result_storage.py` — caps tool result sizes
- Tool results exceeding `max_result_size_chars` are persisted to temp files

---

## 6. Key Files and Responsibilities

| File | Responsibility |
|------|---------------|
| `run_agent.py` | `AIAgent` class (~4,300 lines). Constructor, state, helper methods, thin forwarders to extracted modules |
| `agent/conversation_loop.py` | `run_conversation()` — the main agent loop (~4,200 lines). API calls, response handling, tool dispatch, retry/fallback, compression triggers |
| `agent/tool_executor.py` | `execute_tool_calls_sequential()` and `execute_tool_calls_concurrent()` (~910 lines) |
| `model_tools.py` | Tool orchestration (~920 lines). `get_tool_definitions()`, `handle_function_call()`, `coerce_tool_args()`, async bridging |
| `tools/registry.py` | `ToolRegistry` singleton (~590 lines). Registration, schema retrieval, dispatch, TTL-cached check_fn |
| `toolsets.py` | Toolset definitions and resolution |
| `agent/context_compressor.py` | `ContextCompressor` (~1,750 lines). Pruning, summarization, iterative updates |
| `agent/iteration_budget.py` | `IterationBudget` — thread-safe iteration counter (~60 lines) |
| `agent/tool_dispatch_helpers.py` | Parallelization decision logic, destructive command detection, path overlap checks |
| `agent/prompt_builder.py` | System prompt construction, tool-use enforcement guidance |
| `agent/memory_manager.py` | `StreamingContextScrubber`, memory context blocks, sanitize_context |
| `agent/display.py` | `KawaiiSpinner`, tool preview, cute messages |
| `agent/error_classifier.py` | API error classification for retry/fallback decisions |
| `agent/retry_utils.py` | Jittered backoff calculation |
| `agent/prompt_caching.py` | Anthropic cache_control breakpoint injection |
| `agent/message_sanitization.py` | Surrogate stripping, ASCII sanitization, tool-call argument repair |
| `tools/tool_result_storage.py` | Large tool result persistence, per-turn budget enforcement |

---

## 7. Architecture Observations for Improvement Planning

### Strengths
- Comprehensive error handling and retry logic
- Concurrent tool execution with intelligent parallelization decisions
- Context compression with iterative summarization
- Plugin/hooks extension points at multiple stages
- Session persistence and prefix-cache optimization

### Areas for Improvement (Claude Code comparison)
- **Monolithic conversation_loop.py** (4,200 lines) — the retry/fallback/compression logic is deeply nested and hard to follow
- **Synchronous model** — async tools bridged via thread-per-call; a native async loop would be cleaner
- **No structured tool output protocol** — tool results are raw strings; Claude Code uses typed results
- **Message management is ad-hoc** — messages list mutated throughout; no formal message store abstraction
- **Compression is LLM-dependent** — requires an auxiliary model call; Claude Code's approach may be more deterministic
- **No subagent streaming** — delegated tasks block the parent; no parallel subagent coordination
- **Budget system is simple** — just iteration count; no token-budget or cost-budget awareness
