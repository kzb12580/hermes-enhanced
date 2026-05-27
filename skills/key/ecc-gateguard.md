---
name: ecc-gateguard
description: "Fact-forcing pre-action gate — blocks edits/writes until thorough investigation. Improves quality by +2.25 points. Use before making changes to unfamiliar code."
category: ecc
origin: everything-claude-code
---

# GateGuard

Fact-forcing gate that blocks action until the agent has done real investigation.

## The Problem
Agents (and humans!) often make changes based on assumptions. GateGuard forces investigation first.

## How It Works
Before making any Edit/Write/Bash change, you MUST complete:

### Investigation Checklist
1. **Read the file** — Actually read it, don't assume contents
2. **Check imports** — What does this file depend on?
3. **Find usages** — Who calls this function/module?
4. **Understand data flow** — What goes in, what comes out?
5. **Check tests** — What behavior is expected?
6. **Verify assumptions** — Is what you think true?

### Blocking Rules
❌ DO NOT edit until you have:
- [ ] Read the target file completely
- [ ] Checked all imports and dependencies
- [ ] Found at least 2 usages of the code being changed
- [ ] Verified your assumption about the behavior

✅ DO edit when:
- [ ] You can explain what the code does and why
- [ ] You know who depends on it
- [ ] You've verified your change won't break callers

## Quality Impact
A/B testing showed GateGuard improves code quality by +2.25 points on average by preventing:
- Changes based on wrong assumptions
- Breaking changes to shared utilities
- Incomplete understanding of side effects

## Example

### ❌ Without GateGuard
"I think this function returns a string, let me add .toString()"

### ✅ With GateGuard
1. Read the function → it returns `Result<User, Error>`
2. Check callers → 3 places use `.unwrap()` on it
3. Verify → adding .toString() would break error handling
4. Correct approach → handle the Result properly
