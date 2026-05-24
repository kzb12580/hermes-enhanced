# Claude Code Next Iteration Features — Hermes Upgrade Analysis

## 1. Multi-Tier Context Compaction (compact/)

Claude Code has a sophisticated compaction system with multiple tiers: **autoCompact** (token-count-triggered), **microCompact** (clears old tool results without API calls), **sessionMemoryCompact** (uses session memory for smarter summaries), and **time-based microcompaction** (clears stale file reads by age). The autoCompact layer monitors token usage against model-specific context windows with configurable thresholds and circuit breakers (max 3 consecutive failures). MicroCompact selectively clears tool results from specific tools (FileRead, Shell, Grep, Glob, WebSearch, etc.) while preserving conversation flow. Session memory compaction uses extracted session memories to produce higher-quality summaries with configurable min/max token preservation (10K–40K). **Hermes has basic summarization but lacks multi-tier compaction, micro-compaction of old tool results, and session-memory-aware summarization.** Priority: **HIGH** — context management is critical for long-running tasks.

## 2. Git Worktree Isolation (EnterWorktreeTool/)

The EnterWorktreeTool creates isolated git worktrees in `.claude/worktrees/` and switches the session's working directory into them mid-session. It resolves to the canonical git root, creates a worktree with a new branch, updates all CWD references, clears cached system prompts and memory file caches, and saves worktree state for persistence. It supports both git-native worktrees and VCS-agnostic hooks (WorktreeCreate/WorktreeRemove in settings.json). There's a corresponding ExitWorktree tool. This enables parallel feature development without polluting the main branch. **Hermes has no worktree isolation capability.** Priority: **MEDIUM** — useful for complex multi-task work but not critical for core functionality.

## 3. Cron-Based Scheduled Tasks (ScheduleCronTool/)

Claude Code can schedule recurring or one-shot prompts using standard 5-field cron expressions. Tasks can be **session-only** (in-memory, die on exit) or **durable** (persisted to `.claude/scheduled_tasks.json`, survive restarts). The system includes validation (max 50 jobs, valid cron expressions, calendar date checking), human-readable schedule display, and teammate-aware restrictions (no durable crons for teammates). CronList and CronDelete companion tools manage the lifecycle. **Hermes has no built-in cron scheduling for agent tasks.** Priority: **MEDIUM-HIGH** — enables autonomous recurring workflows and proactive task execution.

## 4. Post-Turn Stop Hooks (stopHooks.ts)

The stopHooks system runs after each agent turn and orchestrates multiple background tasks: **prompt suggestion** (analyzes conversation to suggest next prompts), **memory extraction** (fire-and-forget extraction of memories from the conversation), **job classification** (for template-based dispatched jobs), and **auto-dream** (background memory consolidation). It saves "cache-safe params" for forked agents, handles teammate idle hooks, task-completed hooks, and computer-use cleanup. The system is carefully gated by mode (bare mode skips background work) and query source (main thread vs subagent). It uses AsyncGenerator for streaming hook progress. **Hermes has basic hooks but lacks the orchestrated post-turn background pipeline with memory extraction, prompt suggestion, and job classification.** Priority: **HIGH** — this is the backbone that enables autonomous background intelligence.

## 5. Auto-Dream Background Consolidation (autoDream/)

AutoDream is a background memory consolidation system that fires a forked subagent to review accumulated session transcripts and update long-term memory. It uses a three-gate pattern (cheapest checks first): **time gate** (configurable hours since last consolidation, default 24h), **session gate** (minimum session count since last run, default 5), and **lock gate** (prevents concurrent consolidations via file-based locking with rollback on failure). It runs as a fire-and-forget forked agent with restricted tool access (read-only bash), registers as a DreamTask for UI visibility, and writes consolidated memories to the auto-memory directory. It includes scan throttling (10min between session scans) to avoid expensive filesystem walks every turn. **Hermes has no background memory consolidation or cross-session learning.** Priority: **HIGH** — this is the key differentiator for long-term agent intelligence and continuous improvement.

---

## Priority Summary

| Feature | Priority | Hermes Status |
|---------|----------|---------------|
| Multi-Tier Compaction | HIGH | Missing (basic only) |
| Worktree Isolation | MEDIUM | Missing |
| Cron Scheduling | MEDIUM-HIGH | Missing |
| Post-Turn Hooks Pipeline | HIGH | Partial |
| Auto-Dream Consolidation | HIGH | Missing |

## Recommended Next Steps

1. **Post-Turn Hooks Pipeline** — Build the orchestration layer first; it's the foundation for all background features
2. **Auto-Dream** — Cross-session memory consolidation is the highest-impact missing capability
3. **Multi-Tier Compaction** — Especially micro-compaction (clearing old tool results without API calls) and session-memory-aware summarization
4. **Cron Scheduling** — Enables proactive/autonomous agent behavior
5. **Worktree Isolation** — Lower priority but valuable for development workflows
