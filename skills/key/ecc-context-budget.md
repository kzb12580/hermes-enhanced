---
name: ecc-context-budget
description: "Context window consumption audit — identify bloat, optimize token usage, save costs. Use when context feels crowded or sessions slow down."
category: ecc
origin: everything-claude-code
---

# Context Budget

Audit and optimize context window consumption.

## Why It Matters
- Context window is finite and expensive
- Bloated context = slower responses, higher costs
- Unnecessary content crowds out useful information

## What Consumes Context

| Component | Typical Size | Optimizable? |
|-----------|-------------|-------------|
| System prompt | 2-5K tokens | Yes — trim unused instructions |
| Skills loaded | 1-3K each | Yes — load only needed skills |
| MCP server context | 1-5K each | Yes — disable unused servers |
| CLAUDE.md / AGENTS.md | 1-5K | Yes — keep concise |
| Conversation history | Grows | Yes — compact periodically |
| Tool outputs | Variable | Yes — truncate large outputs |

## Audit Process

### 1. Inventory Loaded Skills
- Which skills are loaded?
- Which were actually used this session?
- Can any be unloaded?

### 2. Check MCP Servers
- Which servers are connected?
- Which tools were called?
- Can any be disabled?

### 3. Review System Prompt
- Any unused instructions?
- Any redundant rules?
- Can sections be condensed?

### 4. Conversation History
- How many turns?
- Any large tool outputs that could be summarized?
- Time to compact?

## Optimization Strategies

### Load Skills Lazily
Don't load all skills upfront. Load on demand based on task.

### Compact at Milestones
After completing a major task, compact the conversation:
```
Summarize what we've done so far in 3-5 bullet points.
Keep: decisions made, files modified, current state.
Discard: intermediate steps, tool output details, debugging traces.
```

### Truncate Tool Output
- Use `limit` parameter on read_file
- Use `head`/`tail` for large files
- Summarize instead of pasting full output

### Prune System Prompt
- Remove instructions for features you never use
- Consolidate similar rules
- Use conditional loading (load rules only when relevant)

## Token Budget Guidelines
| Session Type | Target Budget |
|-------------|--------------|
| Quick question | < 10K tokens |
| Single task | 10-30K tokens |
| Complex project | 30-80K tokens |
| Long session | Compact every 50K tokens |
