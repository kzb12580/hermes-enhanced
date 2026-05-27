---
name: ecc-search-first
description: "Research-before-coding workflow — find existing solutions before writing custom code. Use before implementing any non-trivial feature."
category: ecc
origin: everything-claude-code
---

# Search First

Before writing code, search for existing solutions. Build only when necessary.

## Decision Matrix

| Situation | Action |
|-----------|--------|
| Package exists, well-maintained | **ADOPT** — Install and use |
| Package exists, partial fit | **EXTEND** — Fork or wrap |
| Multiple packages cover parts | **COMPOSE** — Combine |
| Nothing suitable exists | **BUILD** — Write custom |

## Search Checklist

### Package Registries
- npm: `npm search <keyword>`
- PyPI: `pip search <keyword>` or pypi.org
- Go: pkg.go.dev
- Rust: crates.io

### Code Search
- GitHub: Search repos by topic/language
- GitHub: Search code for specific patterns
- MCP servers: Context7 for docs, Exa for web search

### Evaluation Criteria
When considering a package:
- [ ] Last commit within 6 months
- [ ] Open issues reasonable (< 50 for popular packages)
- [ ] Download count indicates adoption
- [ ] License compatible with your project
- [ ] Dependencies are reasonable
- [ ] TypeScript types available (if TS project)
- [ ] Documentation quality

## When to Build Custom
- No existing solution covers your specific case
- Existing solutions have security concerns
- Your use case is core business logic (not infrastructure)
- Existing solution adds 10x more complexity than needed
- Licensing incompatible

## Anti-Patterns
- Building everything from scratch (NIH syndrome)
- Adopting packages without evaluating maintenance status
- Choosing packages based solely on star count
- Ignoring license compatibility
