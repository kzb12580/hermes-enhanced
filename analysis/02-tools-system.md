# Claude Code Tools System — Deep Analysis

## 1. Tool Interface / Base Class Pattern

### The `Tool` Type (src/Tool.ts)

Claude Code does NOT use classes or inheritance for tools. Instead, every tool is a **plain object** conforming to the `Tool<Input, Output, Progress>` TypeScript type — a large interface with ~40+ methods/properties. Tools are built using a **`buildTool()` factory function** that applies sensible defaults.

```typescript
// The core Tool type — key members:
type Tool<Input, Output, P> = {
  name: string
  aliases?: string[]                    // backwards compat when renaming
  searchHint?: string                   // for ToolSearch keyword matching
  maxResultSizeChars: number            // result budget before disk persistence
  strict?: boolean                      // API strict mode
  shouldDefer?: boolean                 // lazy-load via ToolSearch
  alwaysLoad?: boolean                  // never defer
  isMcp?: boolean                       // MCP tool flag
  inputSchema: Input                    // Zod schema
  inputJSONSchema?: ToolInputJSONSchema // for MCP tools
  outputSchema?: z.ZodType

  // Core execution
  call(args, context, canUseTool, parentMessage, onProgress): Promise<ToolResult<Output>>
  description(input, options): Promise<string>
  prompt(options): Promise<string>      // system prompt contribution

  // Validation & permission pipeline
  validateInput?(input, context): Promise<ValidationResult>
  checkPermissions(input, context): Promise<PermissionResult>
  preparePermissionMatcher?(input): Promise<(pattern: string) => boolean>

  // Behavior classification
  isEnabled(): boolean
  isReadOnly(input): boolean
  isConcurrencySafe(input): boolean
  isDestructive?(input): boolean
  interruptBehavior?(): 'cancel' | 'block'
  isSearchOrReadCommand?(input): { isSearch, isRead, isList? }
  isOpenWorld?(input): boolean

  // UI rendering (React/Ink)
  renderToolUseMessage(input, options): React.ReactNode
  renderToolResultMessage?(content, progress, options): React.ReactNode
  renderToolUseProgressMessage?(progress, options): React.ReactNode
  renderToolUseRejectedMessage?(input, options): React.ReactNode
  renderToolUseErrorMessage?(result, options): React.ReactNode
  renderGroupedToolUse?(toolUses, options): React.ReactNode | null

  // Result mapping
  mapToolResultToToolResultBlockParam(content, toolUseID): ToolResultBlockParam
  userFacingName(input): string
  getActivityDescription?(input): string | null
  getToolUseSummary?(input): string | null

  // Auto-mode classifier
  toAutoClassifierInput(input): unknown

  // Hooks integration
  backfillObservableInput?(input): void
  getPath?(input): string
  inputsEquivalent?(a, b): boolean
}
```

### The `buildTool()` Pattern

Every tool uses `buildTool()` which provides fail-closed defaults:

```typescript
export function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D> {
  return {
    ...TOOL_DEFAULTS,          // isEnabled=true, isConcurrencySafe=false, isReadOnly=false
    userFacingName: () => def.name,
    ...def,                    // tool-specific overrides win
  }
}

// Defaults:
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: () => false,   // assume NOT safe
  isReadOnly: () => false,          // assume writes
  isDestructive: () => false,
  checkPermissions: (input) => Promise.resolve({ behavior: 'allow', updatedInput: input }),
  toAutoClassifierInput: () => '',
  userFacingName: () => '',
}
```

This is elegant: tools only define what's non-default. The `satisfies ToolDef` pattern ensures type safety without boilerplate.

---

## 2. Tool Registration & Discovery

### `getAllBaseTools()` — The Master Registry (src/tools.ts)

All tools are registered in a single function that returns the complete tool array:

```typescript
export function getAllBaseTools(): Tools {
  return [
    AgentTool, TaskOutputTool, BashTool,
    ...(hasEmbeddedSearchTools() ? [] : [GlobTool, GrepTool]),  // conditional
    FileReadTool, FileEditTool, FileWriteTool,
    NotebookEditTool, WebFetchTool, TodoWriteTool, WebSearchTool,
    TaskStopTool, AskUserQuestionTool, SkillTool, EnterPlanModeTool,
    // Feature-flagged tools (dead-code-eliminated when off):
    ...(process.env.USER_TYPE === 'ant' ? [ConfigTool, TungstenTool] : []),
    ...(isTodoV2Enabled() ? [TaskCreateTool, TaskGetTool, ...] : []),
    ...(feature('COORDINATOR_MODE') ? [...] : []),
    ...(isAgentSwarmsEnabled() ? [TeamCreateTool, TeamDeleteTool] : []),
    // ... 20+ more conditional tools
  ]
}
```

**Key pattern: Dead code elimination via `feature()` and `require()`.** Feature-flagged tools are conditionally required so they're tree-shaken from the bundle when the flag is off. This is a Bun-specific optimization using `bun:bundle` feature flags.

### Tool Pool Assembly Pipeline

```
getAllBaseTools()           → complete tool list (40+ tools)
    ↓
getTools(permissionContext) → filter by deny rules + isEnabled() + REPL mode
    ↓
assembleToolPool(permCtx, mcpTools) → merge built-in + MCP tools, deduplicate
    ↓
filterToolsForAgent(tools, agentType) → restrict per agent type
```

### Tool Aliases

Tools support `aliases: string[]` for backwards compatibility:
```typescript
// If "KillShell" was renamed to "TaskStop":
{ name: 'TaskStop', aliases: ['KillShell'], ... }
// Lookup: findToolByName() checks name OR aliases
```

### ToolSearch / Deferred Loading

When `shouldDefer: true`, tools are sent to the API with `defer_loading: true`. The model must first call `ToolSearchTool` to discover them. This reduces prompt token count when there are many tools.

---

## 3. Permission System

### Multi-Layer Permission Pipeline

The permission system is the most complex part of the tool architecture. Each tool call passes through:

```
1. Zod Input Validation (tool.inputSchema.safeParse)
2. Tool-specific validateInput() (semantic validation)
3. PreToolUse Hooks (user-defined scripts)
4. Hook Permission Decision (hooks can allow/deny/ask)
5. Rule-based Permission Check (alwaysAllow/alwaysDeny/alwaysAsk rules)
6. Tool-specific checkPermissions() (tool-level logic)
7. canUseTool() — Interactive prompt or auto-mode classifier
8. Tool.call() execution
9. PostToolUse Hooks
```

### Permission Context (`ToolPermissionContext`)

```typescript
type ToolPermissionContext = DeepImmutable<{
  mode: PermissionMode  // 'default' | 'acceptEdits' | 'bypassPermissions' | 'auto' | 'plan'
  additionalWorkingDirectories: Map<string, AdditionalWorkingDirectory>
  alwaysAllowRules: ToolPermissionRulesBySource
  alwaysDenyRules: ToolPermissionRulesBySource
  alwaysAskRules: ToolPermissionRulesBySource
  isBypassPermissionsModeAvailable: boolean
  isAutoModeAvailable?: boolean
  shouldAvoidPermissionPrompts?: boolean  // background agents
}>
```

### Permission Result Types

```typescript
type PermissionResult =
  | { behavior: 'allow'; updatedInput?: ... }     // proceed
  | { behavior: 'deny'; message: string }          // block with error
  | { behavior: 'ask'; message: string; ... }      // prompt user
  | { behavior: 'passthrough' }                     // defer to parent
```

### Tool-Specific Permission Examples

**BashTool**: Has the most complex permission logic — wildcard pattern matching for commands, prefix rules (`git *`), read-only mode validation, sandbox decisions, and an auto-mode classifier.

**FileEditTool/FileWriteTool**: Uses `checkWritePermissionForTool()` with filesystem path-based rules. Expands paths, checks deny rules, and uses `preparePermissionMatcher` for `Bash(git *)` style hook patterns.

**FileReadTool**: Uses `checkReadPermissionForTool()` — read permissions are less restrictive but still enforce path-based rules.

**WebFetchTool**: Domain-based permissions with pre-approved hosts.

**MCPTool**: Permission passthrough — MCP tools delegate to the MCP server's own permission model.

### Permission Rule Matching

Rules are organized by source:
- `session` — temporary grants for this session
- `localSettings` / `userSettings` — persistent user rules
- `policySettings` — organization-level
- `projectSettings` — project `.claude/settings.json`

Each tool can implement `preparePermissionMatcher(input)` to enable pattern matching in hook `if` conditions (e.g., matching `git *` against a bash command).

---

## 4. Tool Execution Flow

### Complete Execution Pipeline (services/tools/toolExecution.ts)

```
runToolUse() — async generator, yields MessageUpdateLazy
  ├── Find tool by name (with alias fallback)
  ├── Check abort signal
  └── streamedCheckPermissionsAndCallTool() — Stream wrapper
      └── checkPermissionsAndCallTool()
          ├── 1. Zod parse input → error if invalid
          ├── 2. tool.validateInput() → error if invalid
          ├── 3. Start speculative classifier (Bash only)
          ├── 4. Backfill observable input (clone for hooks)
          ├── 5. Run PreToolUse hooks
          │   ├── Can return: message, hookPermissionResult, updatedInput, stop
          │   └── Can block execution (hook says "deny")
          ├── 6. Resolve hook permission → runPreToolUseHooks results
          ├── 7. Permission decision (resolveHookPermissionDecision)
          │   ├── If hook decided → use hook result
          │   ├── Else → check rule-based permissions
          │   └── Else → canUseTool() (interactive prompt or auto-classifier)
          ├── 8. If denied → error message + PermissionDenied hooks
          └── 9. If allowed → tool.call(input, context, canUseTool, parentMsg, onProgress)
              ├── Map result to API format
              ├── Apply result size budget (persist to disk if > maxResultSizeChars)
              ├── Run PostToolUse hooks
              └── Return tool result message
```

### Concurrency Model (services/tools/toolOrchestration.ts)

```
partitionToolCalls(toolUseMessages)
  → Batch[] where each batch is:
    - Multiple concurrent-safe tools (read-only), OR
    - Single non-concurrent tool (write operations)

runTools() — processes batches:
  - Concurrent batch → runToolsConcurrently() (up to 10 parallel)
  - Serial batch → runToolsSerially() (one at a time)
```

**Concurrency safety**: Each tool declares `isConcurrencySafe(input)`. Read-only tools (GlobTool, GrepTool, FileReadTool) return `true`; write tools (BashTool, FileEditTool) return `false` by default but can be context-dependent (e.g., `ls` in BashTool).

### StreamingToolExecutor

A newer execution path that starts tools as they stream in from the API:
- Tools are added via `addTool()` as tool_use blocks arrive
- Concurrent-safe tools start immediately in parallel
- Non-concurrent tools wait for exclusive access
- Results are buffered and emitted in order
- Uses a child AbortController so sibling tools die if one errors

---

## 5. Tool Categories (40+ Tools)

### Core File Operations
| Tool | Key Feature |
|------|------------|
| **BashTool** | Shell execution with AST parsing, sandbox, read-only mode |
| **FileReadTool** | Read files, images, PDFs, notebooks; line-numbered output |
| **FileEditTool** | Find-and-replace edits with stale-file detection |
| **FileWriteTool** | Create/overwrite files with diff output |
| **NotebookEditTool** | Jupyter notebook cell editing |

### Search
| Tool | Key Feature |
|------|------------|
| **GrepTool** | ripgrep wrapper with context, head_limit, offset, multiline |
| **GlobTool** | File pattern matching with gitignore awareness |

### Sub-Agent & Task Management
| Tool | Key Feature |
|------|------------|
| **AgentTool** | Spawn sub-agents (sync/async/background, worktree/remote isolation) |
| **TaskCreateTool** | Create tasks in a task list |
| **TaskGetTool** | Get task details |
| **TaskUpdateTool** | Update task status |
| **TaskListTool** | List all tasks |
| **TaskStopTool** | Stop running tasks |
| **TaskOutputTool** | Read task output |
| **TodoWriteTool** | Legacy todo management |
| **SendMessageTool** | Send messages between agents |

### Web Access
| Tool | Key Feature |
|------|------------|
| **WebSearchTool** | Anthropic's built-in web search (beta API) |
| **WebFetchTool** | Fetch URL → markdown with prompt summarization |

### MCP Integration
| Tool | Key Feature |
|------|------------|
| **MCPTool** | Template for MCP server tools (overridden per-server) |
| **ListMcpResourcesTool** | List MCP server resources |
| **ReadMcpResourceTool** | Read MCP server resources |
| **McpAuthTool** | MCP OAuth authentication |
| **ReadMcpResourceTool** | Read MCP resources |

### Planning & Modes
| Tool | Key Feature |
|------|------------|
| **EnterPlanModeTool** | Switch to plan mode (read-only) |
| **ExitPlanModeV2Tool** | Exit plan mode with approval |
| **ConfigTool** | Runtime configuration |

### Multi-Agent / Teams
| Tool | Key Feature |
|------|------------|
| **TeamCreateTool** | Create a team of agents |
| **TeamDeleteTool** | Delete a team |
| **SendMessageTool** | Inter-agent messaging |

### Scheduling & Automation
| Tool | Key Feature |
|------|------------|
| **CronCreateTool** | Create cron jobs |
| **CronDeleteTool** | Delete cron jobs |
| **CronListTool** | List cron jobs |
| **RemoteTriggerTool** | Remote agent triggers |

### Utility
| Tool | Key Feature |
|------|------------|
| **SkillTool** | Invoke markdown-based skills/prompts |
| **ToolSearchTool** | Search for deferred tools |
| **BriefTool** | Brief/summarize content |
| **EnterWorktreeTool** | Git worktree isolation |
| **ExitWorktreeTool** | Clean up worktree |
| **LSPTool** | Language server protocol integration |
| **SyntheticOutputTool** | Synthetic output for testing |

---

## 6. Key Differences from Hermes Agent Tools

| Aspect | Claude Code | Hermes Agent |
|--------|------------|-------------|
| **Tool definition** | Object literal via `buildTool()` | Python class with `@tool` decorator |
| **Schema validation** | Zod (v4) schemas, strict objects | Pydantic models |
| **Type system** | TypeScript generics `<Input, Output, Progress>` | Python type hints |
| **Permission system** | Multi-layer (hooks + rules + classifier + interactive) | Simple allow/deny per tool |
| **UI rendering** | Each tool has React/Ink render methods | Tools return text; UI is separate |
| **Concurrency** | Automatic: `isConcurrencySafe()` → parallel execution | Sequential tool execution |
| **Tool search/deferral** | ToolSearchTool for lazy loading | All tools always loaded |
| **MCP integration** | First-class MCPTool template, dynamic tool creation | MCP client as separate service |
| **Hooks** | PreToolUse/PostToolUse/PermissionRequest hooks | No hook system |
| **Agent delegation** | AgentTool with worktree/remote isolation | Subagent via tool calls |
| **Result size management** | Automatic disk persistence for large results | No result size management |
| **Progress reporting** | Typed progress events (BashProgress, AgentToolProgress, etc.) | Simple status updates |
| **Auto-mode classifier** | ML classifier for auto-approving tool calls | No classifier |
| **File state tracking** | readFileState cache with stale detection | No file state tracking |

---

## 7. Most Interesting / Reusable Patterns

### 7.1 `buildTool()` Factory with Defaults

The `buildTool()` pattern is brilliant. Instead of requiring every tool to implement 40+ methods, tools only define what's non-default. Fail-closed defaults ensure safety:

```typescript
// A minimal tool only needs:
const MyTool = buildTool({
  name: 'my_tool',
  inputSchema: z.object({ ... }),
  async call(input, context) { return { data: result } },
  mapToolResultToToolResultBlockParam(content, id) { return { ... } },
})
```

**Reusable**: Any plugin system could adopt this pattern.

### 7.2 Concurrency-Safe Tool Partitioning

The `partitionToolCalls()` algorithm is elegant:
- Scan tool calls in order
- Group consecutive read-only tools into concurrent batches
- Isolate write tools into serial batches
- Execute concurrently or serially based on batch type

**Reusable**: Any multi-tool execution engine.

### 7.3 File Staleness Detection

FileEditTool and FileWriteTool both:
1. Track `readFileState` with timestamps
2. Before writing, compare `lastWriteTime > readTimestamp`
3. Refuse to write if file was modified since last read
4. On Windows, fall back to content comparison (timestamps unreliable)

**Reusable**: Any code that does read-modify-write on files.

### 7.4 Speculative Classifier Check

BashTool starts the auto-mode classifier **speculatively** (in parallel with pre-tool hooks and permission setup). This hides classifier latency behind other work:

```typescript
if (tool.name === BASH_TOOL_NAME) {
  startSpeculativeClassifierCheck(command, permissionContext, signal, isNonInteractive)
}
```

**Reusable**: Any system where expensive checks can overlap with other work.

### 7.5 Tool Result Size Budget

Results exceeding `maxResultSizeChars` are persisted to disk. The model gets a preview + file path instead of the full content. The `ContentReplacementState` tracks which results have been replaced.

**Reusable**: Any LLM tool system where context window is limited.

### 7.6 Hook System Architecture

The hook system (PreToolUse, PostToolUse, PermissionRequest) allows users to:
- Define shell scripts that run before/after tool calls
- Return JSON to allow/deny/modify tool calls
- Use pattern matching (e.g., `Bash(git *)`) to target specific inputs

**Reusable**: Any extensible tool execution pipeline.

### 7.7 `backfillObservableInput()` Pattern

Before hooks see tool input, a shallow clone is made and `backfillObservableInput()` expands paths (e.g., `~` → absolute). The original model output is preserved for transcript stability:

```typescript
// Clone for hooks/permissions (expanded paths)
const backfilledClone = { ...processedInput }
tool.backfillObservableInput(backfilledClone)

// call() gets the original path (transcript-stable)
// But if a hook modified the input, use that instead
```

**Reusable**: Any system where observers need enriched input but the executor needs raw input.

### 7.8 Agent Tool Isolation Modes

AgentTool supports multiple isolation modes:
- **In-process**: Run in same process (fast, shared state)
- **Worktree**: Git worktree isolation (separate working directory)
- **Remote**: Spawn in remote CCR environment
- **Background**: Async with output file tracking

**Reusable**: Any sub-agent system needing different isolation levels.

### 7.9 Tool Aliases for Backwards Compatibility

When renaming tools, the old name becomes an alias. `findToolByName()` checks both. Old transcripts with deprecated names still work.

**Reusable**: Any API/tool system undergoing evolution.

### 7.10 Streaming Tool Executor

The `StreamingToolExecutor` starts tools as they stream in from the API, rather than waiting for the full response. This reduces latency when multiple tools are called.

**Reusable**: Any system processing streamed tool calls from an LLM.

---

## 8. Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                    API Response Stream                    │
│              (tool_use blocks arrive one by one)          │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              StreamingToolExecutor                        │
│  • Adds tools as they arrive                             │
│  • Starts concurrent-safe tools immediately              │
│  • Buffers results in order                              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              toolOrchestration.ts                         │
│  • partitionToolCalls → concurrent vs serial batches     │
│  • runToolsConcurrently / runToolsSerially               │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              toolExecution.ts                             │
│  1. Zod validation                                       │
│  2. validateInput()                                      │
│  3. PreToolUse hooks                                     │
│  4. Permission check (rules + classifier + interactive)  │
│  5. tool.call()                                          │
│  6. PostToolUse hooks                                    │
│  7. Result size management                               │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Individual Tool (e.g., BashTool)             │
│  • inputSchema: Zod                                      │
│  • validateInput: semantic checks                        │
│  • checkPermissions: tool-specific logic                 │
│  • call: actual execution                                │
│  • mapToolResultToToolResultBlockParam: API format       │
│  • renderToolUseMessage: UI rendering                    │
└─────────────────────────────────────────────────────────┘
```

The tool system is the most architecturally mature part of Claude Code. The `buildTool()` pattern, multi-layer permission pipeline, and concurrency-safe execution are the standout innovations compared to simpler tool systems.
