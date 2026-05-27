---
name: ecc-verification-loop
description: "6-phase verification: build → types → lint → tests → security → diff review. Use before PRs, deployments, or when validating changes."
category: ecc
origin: everything-claude-code
---

# Verification Loop

Systematic verification before shipping code.

## 6-Phase Verification

### Phase 1: Build ✅
```bash
npm run build       # or make build, cargo build, etc.
```
Must complete without errors or warnings.

### Phase 2: Type Check ✅
```bash
npx tsc --noEmit    # TypeScript
mypy src/           # Python
go vet ./...        # Go
```
No type errors allowed.

### Phase 3: Lint ✅
```bash
npm run lint        # ESLint
ruff check src/     # Python
golangci-lint run   # Go
```
Zero warnings for new code.

### Phase 4: Tests ✅
```bash
npm test            # All tests pass
npm run test:coverage  # Coverage >= 80%
```
No skipped tests without justification.

### Phase 5: Security Scan ✅
```bash
npm audit           # Dependency vulnerabilities
bandit -r src/      # Python security
gosec ./...         # Go security
```
No critical/high vulnerabilities.

### Phase 6: Diff Review ✅
```bash
git diff main       # Review all changes
git diff --stat     # File-level summary
```
- No debug code left
- No commented-out code
- No secrets or credentials
- Commit messages follow convention

## Output Format
```markdown
## Verification Report

| Phase | Status | Details |
|-------|--------|---------|
| Build | ✅ PASS | 0 errors, 0 warnings |
| Types | ✅ PASS | Clean |
| Lint  | ✅ PASS | 0 issues |
| Tests | ✅ PASS | 95% coverage |
| Security | ✅ PASS | 0 critical |
| Diff  | ✅ PASS | Clean diff |

### Overall: PASS ✅ — Ready for PR/Deploy
```

## Failure Handling
- **Build fail**: Fix compilation errors first
- **Type fail**: Add missing types, fix type mismatches
- **Lint fail**: Run auto-fix (`--fix` flag), then manual fixes
- **Test fail**: Fix failing tests before new code
- **Security fail**: Update vulnerable deps, fix security issues
- **Diff fail**: Clean up debug code, add missing tests
