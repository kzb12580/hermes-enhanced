---
name: ecc-deep-research
description: "Multi-source deep research with citations. Use when comparing technologies, investigating solutions, or researching best practices."
category: ecc
origin: everything-claude-code
---

# Deep Research Methodology

Systematic approach to technical research with proper source attribution.

## Research Process

### 1. Define Scope
- Core question to answer
- Decisions this will inform
- Time/depth constraints

### 2. Source Hierarchy
1. **Official docs** — Highest trust, version-specific
2. **Source code** — Ground truth for behavior
3. **GitHub issues/discussions** — Real problems and solutions
4. **Technical blogs** — Experienced practitioners
5. **Stack Overflow** — Common patterns (verify!)
6. **Academic papers** — Novel approaches

### 3. Search Strategy
```
Primary:   Official documentation + API reference
Secondary: GitHub repos, issues, PRs
Tertiary:  Blog posts, tutorials, conference talks
Validation: Stack Overflow, Reddit, Discord communities
```

### 4. Extraction Template
For each source:
- **Claim**: What it says
- **Evidence**: Code example, benchmark, or data
- **Version**: When was this written/last updated
- **Credibility**: Author expertise, publication quality

### 5. Synthesis
- Cross-reference findings across 3+ sources
- Identify consensus vs debate
- Note version-specific caveats
- Form evidence-based recommendation

## Output Format
```markdown
## Research: [Topic]

### TL;DR
[2-3 sentence answer]

### Key Findings
1. **[Finding]** — [Evidence] ([Source](url))
2. **[Finding]** — [Evidence] ([Source](url))

### Comparison
| Criteria | Option A | Option B |
|----------|----------|----------|

### Recommendation
[Clear recommendation with reasoning]

### Sources
1. [Name](URL) — [Credibility note]
```

## Quality Rules
- Minimum 3 sources for major claims
- Never fabricate URLs
- Distinguish facts from opinions
- Flag outdated information
- Note conflicting sources
