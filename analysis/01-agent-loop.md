# Claude Code Agent Loop Architecture — Deep Analysis

> Source: `/root/claude-code-study/source-map/restored-src/src/`
> Generated: 2026-05-24

---

## Table of Contents

1. [High-Level Architecture Overview](#1-high-level-architecture-overview)
2. [Entry Points & Bootstrap Flow](#2-entry-points--bootstrap-flow)
3. [The QueryEngine — Session Lifecycle Owner](#3-the-queryengine--session-lifecycle-owner)
4. [The Agent Loop (query.ts)](#4-the-agent-loop-queryts)
5. [Tool Execution Pipeline](#5-tool-execution-pipeline)
6. [Context Management](#6-context-management)
7. [Compaction & Context Window Management](#7-compaction--context-window-management)
8. [Coordinator Mode — Multi-Agent Orchestration](#8-coordinator-mode--multi-agent-orchestration)
9. [Forked Agents & Subagent Context](#9-forked-agents--subagent-context)
10. [State Management](#10-state-management)
11. [Key Design Patterns](#11-key-design-patterns)

---

## 1. High-Level Architecture Overview

Claude Code's agent loop is a **layered async generator pipeline** that processes user input, calls the Anthropic API, executes tools, and manages conversation state across turns. The architecture separates concerns into clear layers:

```
┌─────────────────────────────────────────────────────────────┐
│  CLI / SDK / REPL (entrypoints)                             │
│    └── main.tsx → print.ts (REPL) or QueryEngine (SDK)      │
├─────────────────────────────────────────────────────────────┤
│  QueryEngine (session state owner)                          │
│    └── submitMessage() — async generator yielding SDKMessage │
├─────────────────────────────────────────────────────────────┤
│  query() — the agent loop core (query.ts)                   │
│    └── while(true) { callModel → processTools → continue? } │
├─────────────────────────────────────────────────────────────┤
│  API Layer (claude.ts) + Tool Orchestration                 │
│    └── queryModelWithStreaming + runTools / StreamingToolExec│
├─────────────────────────────────────────────────────────────┤
│  Compaction Layer (auto/micro/snip/reactive/context-collapse)│
├─────────────────────────────────────────────────────────────┤
│  State Layer (AppState store, session storage, transcript)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Entry Points & Bootstrap Flow

### `entrypoints/cli.tsx` — The Bootstrap

The CLI entrypoint is a **fast-path dispatcher** that avoids loading the full module graph for simple operations:

- `--version` → prints version, zero imports
- `--dump-system-prompt` → renders and dumps the system prompt
- `--daemon-worker` → spawns a lean daemon worker
- `daemon` → long-running supervisor process
- `ps/logs/attach/kill` → background session management
- `remote-control` → bridge mode for remote sessions
- Default path → loads `main.tsx` (full CLI)

Key design insight: **every import is dynamic** to minimize module evaluation for fast paths. The `feature()` gate from `bun:bundle` enables build-time dead code elimination.

### `entrypoints/init.ts` — Initialization

The `init()` function (memoized, runs once) handles:

1. **Config validation** (`enableConfigs()`)
2. **Environment setup** (safe env vars, CA certs, proxy, mTLS)
3. **Graceful shutdown** registration
4. **Analytics** (1P event logging, GrowthBook)
5. **OAuth** population
6. **JetBrains detection** (async)
7. **Repository detection** (async)
8. **Remote managed settings** loading
9. **Policy limits** initialization
10. **Telemetry** (deferred until after trust dialog)

Telemetry is lazy-loaded (~400KB of OpenTelemetry) and further deferred for gRPC exporters (~700KB).

### `main.tsx` — The Full CLI

The main entrypoint (4683 lines) builds the React/Ink TUI application, wiring together:
- Commander.js for CLI argument parsing
- React component tree (Ink) for terminal rendering
- AppStateProvider for global state
- REPL loop integration

---

## 3. The QueryEngine — Session Lifecycle Owner

**File:** `QueryEngine.ts` (1295 lines)

The `QueryEngine` class is the **single owner of conversation state** for a session. One instance per conversation; each `submitMessage()` call starts a new turn within that conversation.

### Core Architecture

```typescript
class QueryEngine {
  private config: QueryEngineConfig
  private mutableMessages: Message[]      // conversation history
  private abortController: AbortController // cancellation
  private permissionDenials: SDKPermissionDenial[]
  private totalUsage: NonNullableUsage    // cumulative token usage
  private readFileState: FileStateCache   // file read dedup cache
  private discoveredSkillNames: Set<string>
  private loadedNestedMemoryPaths: Set<string>
}
```

### submitMessage() — The Turn Orchestrator

`submitMessage()` is an **async generator** that yields `SDKMessage` objects. The flow:

1. **Build system prompt** via `fetchSystemPromptParts()`:
   - Default prompt from `getSystemPrompt()` OR custom prompt
   - Memory mechanics prompt (if memory override enabled)
   - Append system prompt
   - Coordinator user context (if coordinator mode)

2. **Process user input** via `processUserInput()`:
   - Handles slash commands (`/compact`, `/model`, etc.)
   - Resolves attachments
   - Determines `shouldQuery` (false for local-only commands)
   - Extracts `allowedTools` from input processing

3. **Persist transcript** before entering query loop (resumability)

4. **Yield system init message** (`buildSystemInitMessage`)

5. **Enter the query loop** via `for await (const message of query(...))`

6. **Process yielded messages** in a state machine:
   - `assistant` → push to mutableMessages, yield normalized
   - `user` → push, yield, increment turn count
   - `progress` → push, yield (for progress tracking)
   - `stream_event` → track usage, yield if partial messages enabled
   - `attachment` → push, handle structured output / max turns / queued commands
   - `system` → handle compact boundaries, API errors, snip replay
   - `tombstone` → skip (control signal for message removal)

7. **Budget enforcement** after each message:
   - USD budget check (`maxBudgetUsd`)
   - Structured output retry limit
   - Max turns check

8. **Yield result** (`success` or `error_*`) with full metrics

### Key Design Decision: AsyncGenerator Pattern

The entire pipeline is built on **async generators**, enabling:
- Streaming: messages are yielded as they arrive
- Composability: `yield*` delegates to sub-generators
- Cancellation: abort signal propagates through the generator chain
- Back-pressure: consumers control when to pull next messages

---

## 4. The Agent Loop (query.ts)

**File:** `query.ts` (1729 lines)

The `query()` function contains the **core agent loop** — a `while(true)` loop that repeatedly calls the model, processes tool results, and decides whether to continue.

### Loop State

```typescript
type State = {
  messages: Message[]              // current conversation messages
  toolUseContext: ToolUseContext    // tool execution context
  autoCompactTracking: AutoCompactTrackingState | undefined
  maxOutputTokensRecoveryCount: number
  hasAttemptedReactiveCompact: boolean
  maxOutputTokensOverride: number | undefined
  pendingToolUseSummary: Promise<ToolUseSummaryMessage | null> | undefined
  stopHookActive: boolean | undefined
  turnCount: number
  transition: Continue | undefined  // why previous iteration continued
}
```

### Single Iteration Flow

Each iteration of the while(true) loop:

```
1. Destructure state
2. Start skill discovery prefetch (async, non-blocking)
3. Apply context management pipeline:
   a. getMessagesAfterCompactBoundary() — trim to post-compact messages
   b. applyToolResultBudget() — enforce per-message tool result size
   c. snipCompactIfNeeded() — remove old conversation segments
   d. microcompactMessages() — compress tool results in-place
   e. applyCollapsesIfNeeded() — context collapse (feature-gated)
   f. autoCompactIfNeeded() — full conversation summarization
4. Build full system prompt (systemPrompt + systemContext)
5. Call model via deps.callModel():
   - prependUserContext() to messages
   - Stream response blocks
   - Track tool_use blocks as they arrive
   - Run streaming tool execution (if enabled)
6. Handle errors:
   - FallbackTriggeredError → switch model, retry
   - ImageSizeError → yield error, return
   - Prompt-too-long → try collapse drain → reactive compact
   - Max-output-tokens → escalate tokens → recovery message
7. Post-response processing:
   - Execute post-sampling hooks
   - Handle abort (yield interruption message)
   - Yield pending tool use summary
8. If no tool_use blocks (needsFollowUp === false):
   - Run stop hooks
   - Check token budget continuation
   - Return { reason: 'completed' }
9. If tool_use blocks exist:
   - Execute tools (streaming or batch)
   - Collect tool results
   - Generate tool use summary (async)
   - Handle abort during tools
   - Get attachment messages (memory, skills, queued commands)
   - Check max turns
   - Build next state, continue loop
```

### Transition Types

The loop tracks `transition: Continue` to record why it continued:

- `next_turn` — normal tool-use continuation
- `reactive_compact_retry` — after reactive compaction
- `collapse_drain_retry` — after context collapse drain
- `max_output_tokens_recovery` — injected recovery message
- `max_output_tokens_escalate` — escalated token limit
- `stop_hook_blocking` — stop hook produced blocking errors
- `token_budget_continuation` — token budget allows more work

### Dependency Injection

```typescript
type QueryDeps = {
  callModel: typeof queryModelWithStreaming
  microcompact: typeof microcompactMessages
  autocompact: typeof autoCompactIfNeeded
  uuid: () => string
}
```

Tests inject fakes via `deps` parameter, avoiding module-level spies.

---

## 5. Tool Execution Pipeline

### `services/tools/toolOrchestration.ts` — Parallel/Serial Partitioning

Tool calls are **partitioned into batches** based on concurrency safety:

```typescript
function partitionToolCalls(toolUseMessages, toolUseContext): Batch[] {
  // Groups consecutive read-only tools into concurrent batches
  // Each write tool gets its own serial batch
}
```

- **Read-only tools** (e.g., Read, Glob, Grep) run concurrently up to `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY` (default: 10)
- **Write tools** (e.g., Edit, Bash) run serially
- Context modifiers from concurrent tools are queued and applied after the batch

### StreamingToolExecutor

When enabled, tools begin executing **as they stream in** from the API:
- Tool blocks are added to the executor as they arrive in the stream
- Results are yielded as they complete (interleaved with streaming)
- On abort, synthetic tool_result blocks are generated for in-progress tools

### Tool Execution Flow (`toolExecution.ts`)

Each tool call goes through:
1. **Permission check** (`canUseTool`) — interactive prompt, auto-approve, or deny
2. **Input validation** via Zod schema
3. **Hook execution** (pre-tool hooks)
4. **Tool execution** (the actual operation)
5. **Result formatting** with size limits
6. **Post-tool hooks**

---

## 6. Context Management

### System Prompt Assembly

The system prompt is built in layers with clear priority:

```
Priority 0: OverrideSystemPrompt (replaces everything)
Priority 1: CoordinatorSystemPrompt (if coordinator mode)
Priority 2: AgentSystemPrompt (if --agent flag)
Priority 3: CustomSystemPrompt (if --system-prompt flag)
Priority 4: DefaultSystemPrompt (standard Claude Code prompt)
Always:    AppendSystemPrompt (added at end)
```

**File:** `utils/systemPrompt.ts` — `buildEffectiveSystemPrompt()`

### User Context & System Context

- **User Context** (`getUserContext()`): prepended to messages via `prependUserContext()`
  - Contains: git status, working directory, platform info
  - Coordinator mode adds `workerToolsContext`

- **System Context** (`getSystemContext()`): appended to system prompt via `appendSystemContext()`
  - Contains: environment details, configuration

### Message Format

Messages flow through normalization:
- `normalizeMessagesForAPI()` — strips UI-only fields for API calls
- `getMessagesAfterCompactBoundary()` — trims to post-compact history
- `prependUserContext()` — adds context before first user message
- `appendSystemContext()` — adds context after system prompt

### Memory & Attachment System

Per-turn, the system injects:
1. **Memory attachments** — relevant memories from CLAUDE.md files, prefetched async
2. **Skill discovery** — found skills from project skill directories
3. **Queued commands** — task notifications, user prompts from message queue
4. **File change attachments** — edited file diffs for context

---

## 7. Compaction & Context Window Management

Claude Code has **five layers** of context management, applied in order:

### 7.1 Tool Result Budget (`applyToolResultBudget`)
- Enforces per-message size limits on tool results
- Replaces oversized results with summaries
- Content replacement state tracks what was replaced

### 7.2 Snip Compact (`snipCompactIfNeeded`)
- Removes old conversation segments beyond a boundary
- Creates `compact_boundary` messages
- Frees tokens before other compaction runs

### 7.3 Microcompact (`microcompactMessages`)
- Compresses individual tool results in-place
- Cached microcompact uses API cache deletion metrics
- Operates on tool_use_id matching (never inspects content)

### 7.4 Context Collapse (`applyCollapsesIfNeeded`)
- Feature-gated (`CONTEXT_COLLAPSE`)
- Commits staged collapses when context pressure builds
- Read-time projection over REPL's full history
- Summary messages live in collapse store, not REPL array

### 7.5 Auto-Compact (`autoCompactIfNeeded`)
- Full conversation summarization when token count exceeds threshold
- Forked agent runs with same cache-safe params (prompt cache sharing)
- Produces `compact_boundary` message with preserved segment info
- Circuit breaker on consecutive failures

### 7.6 Reactive Compact (`tryReactiveCompact`)
- Triggered on prompt-too-long (413) or media-size errors
- Single-shot retry after compaction
- Falls through to surface error if recovery fails

### Recovery Cascade

```
Prompt-too-long error:
  1. Try context collapse drain (cheap, keeps granular context)
  2. Try reactive compact (full summary)
  3. Surface error

Max-output-tokens error:
  1. Try escalating token limit (8k → 64k)
  2. Inject recovery message ("resume directly, break into smaller pieces")
  3. Retry up to MAX_OUTPUT_TOKENS_RECOVERY_LIMIT (3)
  4. Surface error
```

---

## 8. Coordinator Mode — Multi-Agent Orchestration

**File:** `coordinator/coordinatorMode.ts`

Coordinator mode transforms Claude Code into a **task orchestrator** that spawns and manages worker agents.

### Activation
- Environment variable: `CLAUDE_CODE_COORDINATOR_MODE=1`
- Feature gate: `COORDINATOR_MODE`
- Session mode matching on resume (`matchSessionMode`)

### System Prompt

The coordinator gets a completely different system prompt that defines:
- **Role**: Orchestrator, not direct executor
- **Tools**: AgentTool (spawn), SendMessageTool (continue), TaskStopTool (stop)
- **Workflow**: Research → Synthesis → Implementation → Verification
- **Concurrency**: Parallel workers for read-only tasks, serial for writes
- **Worker prompts**: Must be self-contained (workers can't see coordinator conversation)

### Communication Protocol

Workers communicate results via XML notifications:

```xml
<task-notification>
  <task-id>{agentId}</task-id>
  <status>completed|failed|killed</status>
  <summary>{human-readable status summary}</summary>
  <result>{agent's final text response}</result>
  <usage>
    <total_tokens>N</total_tokens>
    <tool_uses>N</tool_uses>
    <duration_ms>N</duration_ms>
  </usage>
</task-notification>
```

### Worker Capabilities

Workers spawned via AgentTool have access to:
- Standard tools (Bash, Read, Edit, etc.)
- MCP tools from connected servers
- Project skills via Skill tool
- Scratchpad directory (if enabled) for cross-worker knowledge sharing

### Key Design Decisions

1. **Workers are autonomous**: Once spawned, they execute independently
2. **Coordinator synthesizes**: Must understand findings before directing follow-up work
3. **Continue vs. Spawn**: Based on context overlap — high overlap → continue, low → spawn fresh
4. **Verification is separate**: Different worker from implementation (fresh eyes)

---

## 9. Forked Agents & Subagent Context

**File:** `utils/forkedAgent.ts`

### Subagent Context Creation

`createSubagentContext()` creates an **isolated ToolUseContext** for subagents:

```typescript
function createSubagentContext(parentContext, overrides?): ToolUseContext {
  return {
    // Cloned mutable state (isolation)
    readFileState: cloneFileStateCache(parent),
    nestedMemoryAttachmentTriggers: new Set(),
    contentReplacementState: cloneContentReplacementState(parent),
    
    // New abort controller (linked to parent)
    abortController: createChildAbortController(parent),
    
    // Isolated getAppState (sets shouldAvoidPermissionPrompts)
    getAppState: () => ({ ...parent.getAppState(), shouldAvoidPermissionPrompts: true }),
    
    // No-op mutation callbacks (prevents interference)
    setAppState: () => {},
    setInProgressToolUseIDs: () => {},
    
    // New agent identity
    agentId: createAgentId(),
    queryTracking: { chainId: randomUUID(), depth: parent.depth + 1 },
  }
}
```

### Cache-Safe Parameters

To share the parent's prompt cache, forked agents use `CacheSafeParams`:

```typescript
type CacheSafeParams = {
  systemPrompt: SystemPrompt      // must match parent
  userContext: { [k: string]: string }
  systemContext: { [k: string]: string }
  toolUseContext: ToolUseContext   // tools, model, thinking config
  forkContextMessages: Message[]  // parent's message prefix
}
```

The Anthropic API cache key is composed of: system prompt + tools + model + messages (prefix) + thinking config. Matching these ensures cache hits.

### `runForkedAgent()` — Independent Query Loop

Runs a complete query loop for forked agents:
1. Creates subagent context from parent
2. Runs `query()` with cache-safe params
3. Tracks usage across all API calls
4. Records sidechain transcript
5. Returns messages + total usage

---

## 10. State Management

### Store Pattern (`state/store.ts`)

A minimal, framework-agnostic store:

```typescript
function createStore<T>(initialState: T, onChange?): Store<T> {
  let state = initialState
  const listeners = new Set<() => void>()
  
  return {
    getState: () => state,
    setState: (updater) => {
      const next = updater(state)
      if (Object.is(next, state)) return  // structural equality
      state = next
      onChange?.({ newState: next, oldState: state })
      for (const listener of listeners) listener()
    },
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener) }
  }
}
```

### AppState (`state/AppStateStore.ts`)

The `AppState` type is a **DeepImmutable** object (~450 lines of type definition) containing:

- **UI state**: verbose, expandedView, footerSelection, spinnerTip
- **Model state**: mainLoopModel, fastMode, effortValue, advisorModel
- **Permission state**: toolPermissionContext (mode, rules, bypass settings)
- **Task state**: tasks (background agents, teammates), agentNameRegistry
- **MCP state**: clients, tools, commands, resources
- **Plugin state**: enabled, disabled, commands, errors, installationStatus
- **Bridge state**: replBridge* (remote control, WebSocket status)
- **Team state**: teamContext, inbox, workerSandboxPermissions
- **History state**: fileHistory, attribution, todos
- **Speculation state**: SpeculationState (prompt suggestion pre-computation)

### React Integration

```typescript
// Subscribe to a slice of state (only re-renders when selected value changes)
const model = useAppState(s => s.mainLoopModel)

// Get setter without subscribing (stable reference)
const setAppState = useSetAppState()

// Get store directly for non-React code
const store = useAppStateStore()
```

### Side Effects (`state/onChangeAppState.ts`)

State changes trigger side effects via the `onChange` callback:
- Permission mode changes → notify CCR/SDK
- Model changes → update settings + override
- Expanded view changes → persist to global config
- Settings changes → clear auth caches, re-apply env vars

### Session Persistence

Messages are persisted to transcript via `recordTranscript()`:
- Written **before** entering query loop (resumability)
- Fire-and-forget for assistant messages (performance)
- Flushed eagerly for cowork mode
- Compact boundaries trigger pre-compaction flush

---

## 11. Key Design Patterns

### 1. AsyncGenerator Pipeline Pattern

The entire flow from user input to response is built on **composable async generators**:

```typescript
// QueryEngine yields SDKMessage
async function* submitMessage(): AsyncGenerator<SDKMessage>

// query() yields StreamEvent | Message | TombstoneMessage
async function* query(): AsyncGenerator<StreamEvent | Message>

// runTools yields MessageUpdate
async function* runTools(): AsyncGenerator<MessageUpdate>

// Each tool yields its result
async function* runToolUse(): AsyncGenerator<MessageUpdateLazy>
```

Benefits: streaming, composability, cancellation propagation, back-pressure.

### 2. State Machine with Explicit Transitions

The query loop uses a `State` type with explicit `transition` field:

```typescript
let state: State = { ... }
while (true) {
  // ... process ...
  state = { ...next, transition: { reason: 'next_turn' } }
  continue
}
```

This makes control flow explicit and testable — tests can assert which transition fired.

### 3. Dependency Injection for Testability

```typescript
type QueryDeps = {
  callModel: typeof queryModelWithStreaming
  microcompact: typeof microcompactMessages
  autocompact: typeof autoCompactIfNeeded
  uuid: () => string
}
```

Production uses `productionDeps()`, tests inject fakes. No module-level spies needed.

### 4. Feature Flags via Build-Time Elimination

```typescript
import { feature } from 'bun:bundle'

// Feature-gated conditional imports
const reactiveCompact = feature('REACTIVE_COMPACT')
  ? require('./services/compact/reactiveCompact.js')
  : null

// Feature-gated runtime checks
if (feature('CONTEXT_COLLAPSE') && contextCollapse) {
  // ...
}
```

`feature()` returns a compile-time constant, enabling tree-shaking of excluded code paths.

### 5. Prompt Cache Sharing via CacheSafeParams

Forked agents (session memory, prompt suggestion, etc.) share the parent's prompt cache by using **identical cache-critical parameters**:

```typescript
type CacheSafeParams = {
  systemPrompt: SystemPrompt      // same bytes
  userContext: { [k: string]: string }
  systemContext: { [k: string]: string }
  toolUseContext: ToolUseContext   // same tools, model, thinking
  forkContextMessages: Message[]  // same prefix
}
```

This is critical for cost efficiency — cache hits avoid re-processing the entire conversation prefix.

### 6. Mutable State Isolation for Subagents

Subagents get **cloned mutable state** to prevent interference:
- `readFileState`: cloned LRU cache
- `contentReplacementState`: cloned replacement decisions
- `abortController`: new child linked to parent (parent abort propagates)
- `setAppState`: no-op (unless explicitly opted in)

### 7. Streaming Tool Execution

Tools can begin executing **before the model finishes streaming**:
- `StreamingToolExecutor` accumulates tool_use blocks as they stream in
- Tools with all required input begin immediately
- Results are interleaved with remaining stream events
- On abort, synthetic tool_results are generated for in-progress tools

### 8. Compaction Cascade

Five independent compaction strategies compose additively:
- Each can run independently or in combination
- Order matters: snip → micro → collapse → auto → reactive
- Each is feature-gated and can be disabled independently
- Circuit breakers prevent infinite retry loops

### 9. Hook System

Three hook points in the agent loop:
- **Pre-tool hooks**: Run before tool execution (permission, validation)
- **Post-sampling hooks**: Run after model response (memory extraction, classification)
- **Stop hooks**: Run after turn completion (linting, testing, prompt suggestion)

Stop hooks can produce **blocking errors** that force the loop to continue with error context.

### 10. Message Queue for Cross-Agent Communication

A process-global message queue enables:
- Task notifications from background agents to coordinator
- User prompts routed to correct agent (main thread vs subagent)
- Priority-based draining (`next` vs `later`)
- Agent-scoped consumption (each agent drains only its own messages)

---

## Summary

Claude Code's agent loop is a sophisticated async generator pipeline that:

1. **Separates concerns** across clear layers (entry, session, loop, tools, state)
2. **Uses async generators** throughout for streaming, composability, and cancellation
3. **Manages context** with five compaction strategies and intelligent prefetching
4. **Supports multi-agent** coordination via coordinator mode and forked agents
5. **Maintains state** through a minimal store with React integration
6. **Optimizes costs** via prompt cache sharing and lazy module loading
7. **Enables extensibility** through hooks, plugins, MCP, and feature flags

The architecture is designed for long-running sessions (hours of continuous use) with aggressive context management, cost optimization, and graceful degradation.
