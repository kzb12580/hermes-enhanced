# 🧠 Hermes Enhanced — Core Skills

预置技能库，涵盖规划、调试、测试、审查、安全等 AI Agent 核心工作流。

## 使用方法

将 `core/` 和 `key/` 目录下的 `.md` 文件复制到 `~/.hermes/skills/` 对应目录即可：

```bash
# 安装所有技能
cp -r skills/core/* ~/.hermes/skills/
cp -r skills/key/* ~/.hermes/skills/

# 只安装核心技能
cp -r skills/core/* ~/.hermes/skills/
```

---

## 🟢 Core — 核心技能 (26)

定义 Hermes Agent 的基础方法论：规划优先、TDD、验证驱动、子代理协作。

- **agents-architect** — Senior software architect — system design, scalability, technical decisions. Load when designing architecture, reviewing system design, or making technology choices.
- **agents-code-reviewer** — Senior code reviewer — quality, security, maintainability. Load when reviewing code, PRs, or doing security audits on any language.
- **agents-code-simplifier** — Code simplification specialist — reduce complexity, improve readability, remove dead code. Load when refactoring, cleaning up code, or reducing technical debt.
- **agents-codebase-onboarding** — Codebase onboarding specialist — rapid analysis of unfamiliar codebases, convention detection, architecture mapping. Load when exploring a new project or helping someone understand a codebase.
- **agents-deep-research** — Deep research specialist — multi-source investigation, synthesis, citations. Load when researching technologies, comparing solutions, or investigating complex topics.
- **agents-doc-updater** — Documentation specialist — codemap generation, README updates, doc synchronization. Load when documentation needs updating, creating codemaps, or syncing docs with code.
- **agents-planner** — Expert planning specialist — complex feature planning, implementation plans, risk identification. Load when breaking down large tasks or planning multi-step implementations.
- **agents-security-reviewer** — Security vulnerability specialist — OWASP Top 10, secrets detection, injection attacks. Load for security audits, vulnerability scanning, or pre-deployment checks.
- **agents-silent-failure-hunter** — Silent failure detection — swallowed errors, empty catches, bad fallbacks, missing error propagation. Load when debugging mysterious failures or auditing error handling.
- **agents-tdd-guide** — Test-Driven Development specialist — Red-Green-Refactor, 80%+ coverage, edge cases. Load when writing tests, setting up test infrastructure, or enforcing TDD.
- **brainstorming** — 在任何创造性工作之前必须使用此技能——创建功能、构建组件、添加功能或修改行为。在实现之前先探索用户意图、需求和设计。
- **dispatching-parallel-agents** — 当面对 2 个以上可以独立进行、无共享状态或顺序依赖的任务时使用
- **executing-plans** — 当你有一份书面实现计划需要在单独的会话中执行，并设有审查检查点时使用
- **finishing-a-development-branch** — 当实现完成、所有测试通过、需要决定如何集成工作时使用——通过提供合并、PR 或清理等结构化选项来引导开发工作的收尾
- **mcp-builder** — MCP 服务器构建方法论 — 系统化构建生产级 MCP 工具，让 AI 助手连接外部能力
- **receiving-code-review** — 收到代码审查反馈后、实施建议之前使用，尤其当反馈不明确或技术上有疑问时——需要技术严谨性和验证，而非敷衍附和或盲目执行
- **requesting-code-review** — 完成任务、实现重要功能或合并前使用，用于验证工作成果是否符合要求
- **subagent-driven-development** — 当在当前会话中执行包含独立任务的实现计划时使用
- **systematic-debugging** — 遇到任何 bug、测试失败或异常行为时使用，在提出修复方案之前执行
- **test-driven-development** — 在实现任何功能或修复 bug 时使用，在编写实现代码之前
- **using-git-worktrees** — 当需要开始与当前工作区隔离的功能开发或执行实现计划之前使用——创建具有智能目录选择和安全验证的隔离 git 工作树
- **using-superpowers** — 在开始任何对话时使用——确立如何查找和使用技能，要求在任何响应（包括澄清性问题）之前调用 Skill 工具
- **verification-before-completion** — 在宣称工作完成、已修复或测试通过之前使用，在提交或创建 PR 之前——必须运行验证命令并确认输出后才能声称成功；始终用证据支撑断言
- **workflow-runner** — 在 Claude Code / OpenClaw / Cursor 中直接运行 agency-orchestrator YAML 工作流——无需 API key，使用当前会话的 LLM 作为执行引擎。当用户提供 .yaml 工作流文件或要求多角色协作完成任务时触发。
- **writing-plans** — 当你有规格说明或需求用于多步骤任务时使用，在动手写代码之前
- **writing-skills** — 当创建新技能、编辑现有技能或在部署前验证技能是否有效时使用

## 🔵 Key — 关键技能 (23)

语言审查、最佳实践模式、核心工作流工具。

- **agents-python-reviewer** — Python specialist — PEP 8, type hints, async, Django/FastAPI patterns. Load when reviewing Python code.
- **agents-typescript-reviewer** — TypeScript/JavaScript specialist — type safety, async patterns, Node.js and React best practices. Load when reviewing TS/JS code.
- **ecc-codebase-onboarding** — 4-phase codebase analysis: reconnaissance → architecture mapping → convention detection → guide generation. Use when exploring an unfamiliar project.
- **ecc-context-budget** — Context window consumption audit — identify bloat, optimize token usage, save costs. Use when context feels crowded or sessions slow down.
- **ecc-deep-research** — Multi-source deep research with citations. Use when comparing technologies, investigating solutions, or researching best practices.
- **ecc-gateguard** — Fact-forcing pre-action gate — blocks edits/writes until thorough investigation. Improves quality by +2.25 points. Use before making changes to unfamiliar code.
- **ecc-search-first** — Research-before-coding workflow — find existing solutions before writing custom code. Use before implementing any non-trivial feature.
- **ecc-security-review** — Security checklist for auth, input validation, injection, CSRF, rate limiting, secrets management. Use before deployment or when adding auth/payment features.
- **ecc-tdd-workflow** — TDD methodology with Red-Green-Refactor cycle, 80%+ coverage enforcement, mocking patterns. Use when developing new features or fixing bugs.
- **ecc-verification-loop** — 6-phase verification: build → types → lint → tests → security → diff review. Use before PRs, deployments, or when validating changes.
- **gstack-careful** — |
- **gstack-context-restore** — |
- **gstack-context-save** — |
- **gstack-cso** — |
- **gstack-freeze** — |
- **gstack-guard** — |
- **gstack-health** — |
- **gstack-investigate** — |
- **gstack-learn** — |
- **gstack-qa** — |
- **gstack-review** — |
- **gstack-ship** — |
- **proxy-rule-sets** — Create and maintain China-optimized proxy rule sets for sing-box, Clash (mihomo), and V2Ray/Xray. Includes DNS split, WebRTC leak prevention, fake-ip filtering, and GitHub Actions auto-update.

---

## 技能分类说明

- **Core**: 定义 Agent 的思维方式和工作方法论，不可或缺
- **Key**: 高频使用的语言审查、安全检查、工作流工具
- **Nice-to-have**: 领域专用技能（iOS、设计、中文适配等），按需安装