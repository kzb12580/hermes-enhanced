---
name: ecc-codebase-onboarding
description: "4-phase codebase analysis: reconnaissance → architecture mapping → convention detection → guide generation. Use when exploring an unfamiliar project."
category: ecc
origin: everything-claude-code
---

# Codebase Onboarding

Rapidly understand an unfamiliar codebase.

## Phase 1: Reconnaissance (5 min)

### Quick Wins
```bash
# Project identity
cat README.md | head -50
cat package.json | jq '.name, .description, .scripts'
cat pyproject.toml | head -30
cat go.mod | head -20

# Structure
tree -L 2 -I 'node_modules|.git|dist|build|__pycache__'

# Size
find . -name '*.ts' -o -name '*.py' -o -name '*.go' | wc -l
wc -l $(find . -name '*.ts' -not -path '*/node_modules/*') | tail -1
```

### Entry Points
Look for: main.ts, index.ts, app.py, main.go, cmd/, server/

## Phase 2: Architecture Mapping (10 min)

### Trace the Request Flow
1. Find the entry point
2. Follow the main request path
3. Identify layers (route → controller → service → data)
4. Map external integrations (DB, cache, APIs)

### Key Questions
- How is routing configured?
- Where is business logic?
- How is data accessed?
- What's the error handling pattern?
- How is authentication done?

## Phase 3: Convention Detection (5 min)

### Code Style
- Naming: camelCase? snake_case?
- File organization: by feature or by type?
- Import style: relative or absolute?

### Patterns
- Error handling: try/catch, Result types, error middleware?
- Validation: decorators, schemas, middleware?
- Testing: framework, naming, location?

### Git Conventions
```bash
git log --oneline -20   # Commit message style
cat .gitignore          # What's excluded
ls .github/workflows/   # CI setup
```

## Phase 4: Generate Guide

Output a structured document covering:
- What the project does
- Tech stack and versions
- Project structure with purpose of each directory
- Key files and their roles
- Architecture (how layers connect)
- Conventions observed
- Common tasks (how to add a feature, run tests, etc.)
- Gotchas and non-obvious things

## Variant: Reference-Based Code Analysis

When the goal is NOT to work on the codebase, but to study it as a reference to improve your own project. This is a distinct workflow from onboarding.

### Trigger
"Study X to improve our Y", "find the source for Z and analyze it", "reverse engineer X for reference"

### Workflow

1. **Find the source** — See `references/github-source-recovery.md` for search patterns (npm source maps, deobfuscation repos, `gh search`). Clone the best-maintained restoration.

2. **Set up study workspace** — Create a separate directory (e.g. `~/project-study/`). Critical pitfalls:
   - Remove nested `.git/` dirs from cloned repos before adding to parent: `rm -rf cloned-repo/.git`
   - Exclude heavy artifacts in `.gitignore`: `node_modules/`, `*.tgz`, compiled bundles, `package/` (npm tarball contents)
   - Only include the restored/deobfuscated source, not the full npm package

3. **Deep analysis via parallel subagents** — For large codebases (1000+ files), delegate 3 parallel analyses to subagents, each covering a distinct concern:
   - Agent 1: Core loop / agent architecture (entrypoints, coordinator, state)
   - Agent 2: Tool system (tool interfaces, registration, permissions, execution)
   - Agent 3: Infrastructure / services (API client, MCP, memory, CLI, plugins)
   Each agent writes its findings to `analysis/NN-topic.md` in the study workspace.

4. **Create private GitHub repo** — Push analysis reports + reference source:
   ```bash
   gh repo create owner/repo-name --private --description "..."
   git init && git remote add origin <url> && git add -A && git commit -m "init: ..." && git push -u origin main
   ```

5. **Generate comparison & upgrade plan** — Compare the reference architecture against your own. Document in `iteration/upgrade-plan.md`:
   - P0 (immediate): Patterns you can adopt now with minimal refactoring
   - P1 (medium): Patterns requiring moderate restructuring
   - P2 (long-term): Architectural shifts requiring significant work

6. **Isolate from production** — The study workspace and any iteration code must NOT touch the running production codebase. Use a separate directory. Test on non-production servers.

6. **Implement improvements via CEO delegation** — Don't write all code yourself. Design the architecture, then delegate each module to a parallel subagent:
   - Write an `__init__.py` with the architecture design doc (interfaces, data flow, priority)
   - Each subagent gets: clear requirements, interface spec, test expectations, output file path
   - All modules should be stdlib-only (no external deps) for easy deployment
   - Each module gets its own test file with 30+ tests

7. **Multi-model code review** — After implementation, delegate a code review to a separate subagent. Different models catch different bugs. The reviewer outputs MUST_FIX / SHOULD_FIX / NICE_TO_HAVE. Then delegate fixes to another subagent. Verify all tests still pass.

8. **Remote server testing** — Deploy to non-production servers for environment validation:
   ```bash
   scp -r module/ user@server:/path/to/test/
   ssh user@server "cd /path && python3 -m pytest tests/ -v"
   ```
   Different environments (OS, Python version, missing deps) surface different issues.

9. **Push & report** — Commit fixes, push to private repo, write test report documenting: environment, results, bugs found/fixed, next steps.

### Pitfalls
- **Don't touch production code** until modules are tested in isolation
- **pip install on fresh servers** may hit PEP 668 — use `--break-system-packages` or venv
- **Nested .git dirs** — remove cloned repos' `.git/` before adding to parent repo
- **Large npm packages** — exclude `node_modules/`, `*.tgz`, compiled bundles from git
- **Subagent timeouts** — complex implementation tasks may need 300s+ timeout; if interrupted, break into smaller tasks

### Key Differences from Standard Onboarding
| Aspect | Onboarding | Reference Analysis |
|--------|-----------|-------------------|
| Goal | Work on this code | Learn from this code |
| Depth | Understand enough to contribute | Extract patterns for your own project |
| Output | Internal guide | Comparison + upgrade plan + implementation |
| Scope | One codebase | Two codebases (reference + yours) |
| Workspace | In or near the project | Separate isolated directory |
| Execution | You code | Subagents code, you decide |

## Quality Rules
- All paths verified to exist
- Commands tested
- Conventions from code, not assumptions
- Honest about unknowns

## Reference Files
- `references/github-source-recovery.md` — Techniques for finding leaked/deobfuscated source on GitHub (npm source maps, gh search patterns, quality signals)
- `references/claude-code-architecture.md` — Claude Code v2.1.88 architecture reference (agent loop, tool system, compression, services, design patterns)
