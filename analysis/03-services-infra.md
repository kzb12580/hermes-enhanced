# Claude Code Services & Infrastructure Analysis

## 1. API Client Architecture

### Provider Abstraction (`src/services/api/client.ts`)

The API client uses a **multi-provider factory pattern** that returns a unified `Anthropic` interface regardless of the underlying cloud provider:

- **Direct API (first-party)**: Uses `@anthropic-ai/sdk` with API key or OAuth token
- **AWS Bedrock**: Uses `@anthropic-ai/bedrock-sdk` with AWS credential refresh
- **GCP Vertex AI**: Uses `@anthropic-ai/vertex-sdk` with Google Auth Library
- **Azure Foundry**: Uses `@anthropic-ai/foundry-sdk` with Azure AD token provider

Provider selection is environment-variable driven:
- `CLAUDE_CODE_USE_BEDROCK` → Bedrock
- `CLAUDE_CODE_USE_VERTEX` → Vertex
- `CLAUDE_CODE_USE_FOUNDRY` → Foundry
- Otherwise → Direct API

Each provider has its own credential refresh mechanism (OAuth, AWS STS, GCP metadata, Azure AD). The client injects custom headers (`x-app: cli`, session ID, container ID) and wraps fetch with a UUID-based client request ID for server-side log correlation.

### Streaming & Query Architecture (`src/services/api/claude.ts`)

The main query function `queryModelWithStreaming` (~3400 lines) is the heart of the system:

- Uses `@anthropic-ai/sdk`'s streaming API (`BetaRawMessageStreamEvent`)
- Supports **extended thinking** (adaptive and fixed budget) via `ThinkingConfig`
- Manages **prompt caching** with ephemeral/1h TTL, global scope, and cache break detection
- Supports **task budgets** (token-aware output limits)
- Handles **tool search** (deferred tools, tool discovery)
- Manages **advisor models** (secondary model for advice)
- Supports **fast mode** (rate-limited speed tier with cooldown/fallback)
- Implements **effort levels** (string or numeric, beta-gated)
- Includes **anti-distillation** measures for 1P builds

The streaming flow processes content blocks, thinking blocks, tool use blocks, and tool results, emitting `StreamEvent` objects consumed by the REPL.

### Retry System (`src/services/api/withRetry.ts`)

Sophisticated retry logic with multiple strategies:

- **Default max retries**: 10 attempts with exponential backoff (base 500ms)
- **529 overload handling**: Foreground queries retry up to 3 times; background queries bail immediately to prevent "capacity cascade" amplification
- **Model fallback**: After 3 consecutive 529s, triggers fallback from Opus → Sonnet
- **Fast mode fallback**: On 429/529, either short retry (preserve cache) or cooldown (switch to standard speed)
- **Persistent retry mode** (`CLAUDE_CODE_UNATTENDED_RETRY`): For unattended sessions, retries indefinitely with 5-minute max backoff and 6-hour cap, yielding heartbeat messages to prevent idle detection
- **Auth error recovery**: On 401, forces OAuth token refresh and gets a fresh client
- **Stale connection handling**: On ECONNRESET/EPIPE, disables keep-alive and reconnects
- **Context overflow**: On max_tokens errors, adjusts max_tokens for retry

### Error Classification (`src/services/api/errors.ts`)

Comprehensive error taxonomy:
- Authentication errors (invalid key, revoked token, disabled org)
- Rate limits (5hr/7day limits, overage status, opus-specific)
- Media errors (image too large, PDF too large/password-protected)
- Prompt too long (with token count parsing for reactive compact)
- Connection timeouts
- Tool use/result mismatch diagnostics

---

## 2. MCP Integration (`src/services/mcp/`)

### Architecture

MCP (Model Context Protocol) integration is a full-featured client implementation using `@modelcontextprotocol/sdk`:

**Transport types supported:**
- **stdio**: Spawns child processes (`StdioClientTransport`)
- **SSE**: Server-Sent Events (`SSEClientTransport`)
- **HTTP**: Streamable HTTP (`StreamableHTTPClientTransport`)
- **WebSocket**: Custom WS transport with `mcp` protocol
- **SDK**: In-process transport for IDE extensions (`SdkControlTransport`)
- **claudeai-proxy**: Proxy through claude.ai with OAuth bearer tokens

**Connection management** (`MCPConnectionManager.tsx`):
- React context-based connection manager
- Supports reconnect and toggle (enable/disable) per server
- Connections managed via `useManageMCPConnections` hook

**Server configuration** (`config.ts`):
- Multi-scope config: local, user, project, dynamic, enterprise, claudeai, managed
- `.mcp.json` file with atomic write (temp + rename)
- Enterprise policy: allowlist/denylist by name, command, or URL pattern
- Plugin MCP server deduplication (signature-based: `stdio:cmd` or `url:url`)
- Claude.ai connector dedup against manual servers
- CCR proxy URL unwrapping for remote sessions

**Tool integration**:
- MCP tools wrapped as `MCPTool` instances
- Tool descriptions capped at 2048 chars
- Binary content persisted to disk (images, blobs)
- Elicitation handler for interactive MCP server prompts
- OAuth auth flow with PKCE, token caching (15min TTL), and auth error recovery

### Auth System (`src/services/mcp/auth.ts`)

- OAuth 2.0 with PKCE for remote MCP servers
- Cross-App Access (XAA) support via IdP connection
- Step-up detection for auth challenges
- Keychain-based secure storage for tokens

---

## 3. Plugin System (`src/services/plugins/`)

### Design

Plugins extend Claude Code with custom skills, MCP servers, and hooks:

**Installation** (`pluginOperations.ts`):
- Scoped installation: user, project, local, managed
- Marketplace-based discovery and resolution
- Dependency resolution with reverse-dependency tracking
- Policy-based blocking (enterprise managed settings)
- V2 installed_plugins.json tracking (independent of marketplace state)
- Settings-first: writes settings (declares intent), then caches plugin

**Background installation** (`PluginInstallationManager.ts`):
- Non-blocking startup: reconciles declared vs materialized marketplaces
- Auto-refresh on new installs; notification for updates
- Progress tracking via AppState updates

**Plugin lifecycle**:
- Install → Enable → Load → Execute
- Uninstall removes from settings + installed_plugins + data directory
- Enable/disable toggles in settings (scope-aware)
- Update checks marketplace for newer versions

**CLI commands** (`pluginCliCommands.ts`):
- `claude plugin install/uninstall/enable/disable/update`
- Scope flags (--scope user/project/local)

---

## 4. Conversation Compaction (`src/services/compact/`)

### Multi-Level Compaction Strategy

Claude Code implements a **three-tier compaction system** to manage context window pressure:

#### Level 1: Microcompact (`microCompact.ts`)
- **Time-based**: When gap since last assistant message exceeds threshold, clears old tool result content (replaces with `[Old tool result content cleared]`)
- **Cached microcompact** (ant-only): Uses cache editing API (`cache_edits` blocks) to remove tool results without invalidating the cached prefix. Tracks tool results per user message and queues deletions.
- Only targets specific tools: FileRead, Bash, Grep, Glob, WebSearch, WebFetch, FileEdit, FileWrite
- Operates before API requests to minimize context size

#### Level 2: Auto-compact (`autoCompact.ts`)
- Triggers when token count exceeds `contextWindow - 13K tokens`
- Circuit breaker: stops after 3 consecutive failures
- **Session memory compact** tried first (lighter-weight)
- Falls back to full conversation compaction
- Recursion guards prevent deadlock (won't fire for session_memory/compact sources)
- Respects context collapse mode (when enabled, collapse manages headroom)

#### Level 3: Full Compaction (`compact.ts`)
- Uses forked agent pattern (shares parent's prompt cache)
- **Prompt structure**: Detailed analysis → summary with 9 sections (Primary Request, Key Concepts, Files/Code, Errors/Fixes, Problem Solving, User Messages, Pending Tasks, Current Work, Next Step)
- Strips images/documents before summarizing
- Post-compact: restores key files (up to 5, 5K tokens each), re-injects skills (25K budget), session memory, and file attachments
- Handles prompt-too-long during compaction itself (truncates oldest API-round groups)
- Pre/post compact hooks for extensibility

### Compaction Prompts (`prompt.ts`)
- Aggressive "NO TOOLS" preamble to prevent tool calls during summarization
- `<analysis>` scratchpad stripped from final summary
- Custom instructions support (user + hook-merged)
- Partial compact variants: `from` (recent-only) and `up_to` (prefix for continuing)

---

## 5. Memory Extraction (`src/services/extractMemories/`)

### Architecture

Background memory extraction runs as a **forked subagent** after each complete query loop:

**Execution model**:
- Uses `runForkedAgent` — perfect fork sharing parent's prompt cache
- Closure-scoped state (cursor UUID, overlap guard, in-progress flag)
- Coalescing: if extraction is in-progress, stashes context for one trailing run
- Throttled: runs every N eligible turns (configurable via GrowthBook)
- Max 5 turns per extraction (prevents rabbit-holes)

**Tool permissions**:
- Restricted to: Read, Grep, Glob, read-only Bash, Edit/Write within memory directory only
- REPL tool allowed (inner primitives re-checked)

**Memory taxonomy** (4 types):
- User preferences and feedback
- Project conventions and patterns
- Technical discoveries
- Workflow observations

**Storage**:
- Each memory in its own file with frontmatter (type, topic, tags)
- `MEMORY.md` index file (kept under 200 lines)
- Team memory support (shared vs private directories)
- Manifest injection so agent knows existing files

**Mutual exclusion**: When the main agent writes memories directly, the forked extraction skips that turn.

---

## 6. Session Memory (`src/services/SessionMemory/`)

### Design

Session memory maintains a structured markdown file for the current conversation:

**Template structure** (9 sections):
- Session Title, Current State, Task Specification, Files/Functions, Workflow, Errors & Corrections, Codebase Documentation, Learnings, Key Results, Worklog

**Triggering**:
- Initialization threshold: minimum token count before first extraction
- Update thresholds: both token growth AND tool call count must be met
- OR: token threshold met + no tool calls in last turn (natural break)
- Sequential execution (prevents overlapping extractions)

**Extraction**:
- Forked subagent with Edit-only permission on the memory file
- Customizable template and prompt (`~/.claude/session-memory/config/`)
- Section size limits (2K tokens per section, 12K total)
- Automatic condensation when over budget

**Compaction integration**:
- Session memory used as lighter alternative to full compaction
- `trySessionMemoryCompaction` prunes messages based on session memory state
- `lastSummarizedMessageId` tracked for incremental updates

---

## 7. CLI/Server/Bridge Architecture

### CLI (`src/cli/`)

**Transport layer** supports multiple connection modes:

- **SSETransport**: HTTP-based SSE for reads, HTTP POST for writes. Reconnect with exponential backoff (1s base, 30s max, 10min budget). Liveness timeout at 45s.
- **WebSocketTransport**: Persistent WS connection for bidirectional communication
- **HybridTransport**: WebSocket reads + HTTP POST writes. Uses `SerialBatchEventUploader` for serialized, batched, retried writes. Stream events buffered 100ms before POST.
- **CCR Client**: Claude Code Remote client for cloud sessions

**Key patterns**:
- NDJSON-safe stringification for transport
- Structured IO for SDK-style message passing
- Remote IO for bridge-connected sessions

### Server Mode (`src/server/`)

**Direct Connect** (`directConnectManager.ts`):
- WebSocket-based session management
- Handles SDK messages, permission requests, interrupts
- JSON-RPC style request/response for control flow
- Used for IDE integration and remote control

**Session types**:
- `DirectConnectSessionManager`: WebSocket client connecting to a server
- Supports bidirectional: send messages, receive permission requests, respond to controls

### Bridge (`src/bridge/`)

The bridge enables **Claude Code Remote (CCR)** — running Claude Code sessions in cloud environments:

**Two modes**:

1. **Environment-based** (`bridgeMain.ts`): Full lifecycle with Environments API
   - Register worker → Poll for work → Spawn session → Heartbeat → Archive
   - Multi-session support (up to 32 concurrent sessions)
   - Worktree isolation per session
   - Capacity-based and spawn-based modes
   - Token refresh scheduling (proactive 5min before expiry)
   - Status display with per-session activity tracking

2. **Env-less** (`remoteBridgeCore.ts`): Direct session-ingress connection
   - POST /v1/code/sessions → POST /bridge → SSE transport
   - No Environments API layer
   - JWT refresh via /bridge re-call (bumps epoch)
   - Echo dedup with bounded UUID sets
   - FlushGate for ordered history + live writes

**Transport rebuild**: On 401 or proactive refresh, transport is fully rebuilt with new JWT/epoch (not just token swap — epoch must change).

**Bridge messaging** (`bridgeMessaging.ts`):
- Handles ingress messages, server control requests
- Result message formatting
- Title extraction from user messages

---

## 8. Skills System (`src/skills/bundled/`)

### Design

Skills are **prompt-based commands** that extend Claude Code's capabilities:

**Registration pattern**:
```typescript
registerBundledSkill({
  name: 'verify',
  description: '...',
  userInvocable: true,
  files: SKILL_FILES,  // Associated file paths
  async getPromptForCommand(args) {
    return [{ type: 'text', text: PROMPT }];
  },
});
```

**Built-in skills** (17 registered):
- `verify`: Code verification by running the app
- `remember`: Memory review and promotion to CLAUDE.md
- `debug`: Debugging assistance
- `simplify`: Code simplification
- `skillify`: Create new skills from patterns
- `keybindings`: Keyboard shortcut reference
- `updateConfig`: Configuration management
- `batch`: Batch operations
- `stuck`: Get unstuck guidance
- `loremIpsum`: Test content generation
- `claudeApi`: Claude API integration (BUILDING_CLAUDE_APPS)
- `claudeInChrome`: Browser integration
- `loop`: Scheduled/cron execution (AGENT_TRIGGERS)
- `scheduleRemoteAgents`: Remote agent scheduling (AGENT_TRIGGERS_REMOTE)
- `dream`: Background processing (KAIROS)

**Feature gating**: Skills conditionally registered based on `feature()` flags (dead code elimination).

**MCP skills**: Skills can also be fetched from MCP servers (`fetchMcpSkillsForClient`).

---

## 9. Command System (`src/types/command.ts`)

### Command Types

Commands are the slash-command system (`/command`):

**Three command types**:

1. **PromptCommand** (`type: 'prompt'`):
   - Returns content blocks injected into conversation
   - Has `progressMessage`, `contentLength`, `argNames`
   - Can specify `allowedTools`, `model`, `effort`
   - Supports `context: 'inline'` or `context: 'fork'` (sub-agent)
   - Source tracking: builtin, mcp, plugin, bundled

2. **LocalCommand** (`type: 'local'`):
   - Lazy-loaded module with `call(args, context)` → `LocalCommandResult`
   - Returns text, compact result, or skip
   - Supports non-interactive mode

3. **LocalJSXCommand** (`type: 'local-jsx'`):
   - Lazy-loaded React component
   - Full UI rendering with `onDone` callback
   - Can trigger model queries, insert meta messages, chain commands

**Command features**:
- `availability`: Auth-type gating (claude-ai, console)
- `isEnabled()`: Runtime feature flag checks
- `isHidden`: Hidden from typeahead/help
- `aliases`: Alternative names
- `whenToUse`: Model-invocation guidance
- `disableModelInvocation`: Prevent model from calling
- `userInvocable`: Whether users can type /name
- `immediate`: Bypass execution queue
- `isSensitive`: Redact args from history
- `kind: 'workflow'`: Workflow-backed (badged in autocomplete)

**Command sources**: Built-in, skills directory, plugins, MCP servers, managed settings

---

## Key Architectural Patterns

### 1. Forked Agent Pattern
Used extensively (compaction, memory extraction, session memory): creates a perfect fork of the main conversation that shares the parent's prompt cache. The fork runs with restricted tool permissions and a turn budget.

### 2. Feature Flags & Dead Code Elimination
`feature('FLAG_NAME')` from `bun:bundle` gates code at build time. Feature-gated imports use conditional `require()` to avoid pulling heavy dependencies into external builds.

### 3. GrowthBook Integration
Remote configuration via GrowthBook for A/B testing and gradual rollouts. Values cached with `_CACHED_MAY_BE_STALE` suffix pattern for non-blocking reads.

### 4. Closure-Scoped State
Mutable state captured in closures (e.g., `initExtractMemories()`, `initSessionMemory()`) rather than module-level globals. Enables test isolation via `beforeEach` reset.

### 5. Sequential Execution
`sequential()` wrapper prevents overlapping async operations (session memory extraction).

### 6. Atomic File Writes
Config files written via temp file + rename pattern with permission preservation.

### 7. Echo Dedup
Bridge implementations track posted UUIDs in bounded sets to prevent server echoes from being re-processed as new messages.

### 8. Transport Abstraction
Multiple transport implementations (SSE, WebSocket, Hybrid) behind a common interface, with automatic reconnection, batching, and backpressure.
