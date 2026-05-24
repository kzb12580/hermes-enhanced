# Claude Code 源码分析 & Hermes Agent 迭代参考

> 基于 Claude Code npm v2.1.88 source map 还原的完整源码分析

## 📁 仓库结构

```
claude-code-study/
├── analysis/                    # 深度架构分析报告
│   ├── 01-agent-loop.md        # Agent循环核心架构
│   ├── 02-tools-system.md      # 工具系统设计
│   └── 03-services-infra.md    # 基础设施与服务层
├── source-map/                  # ChinaSiro/claude-code-sourcemap (源码还原)
│   └── restored-src/src/       # 1332个TypeScript文件, 38万行
├── source-study/                # luyao618/Claude-Code-Source-Study (研究版)
└── iteration/                   # 迭代方案与实现计划
    └── upgrade-plan.md          # Hermes Agent升级方案
```

## 🔍 核心发现

### Agent循环 (query.ts)
- **AsyncGenerator Pipeline**: 全流程使用可组合异步生成器
- **while(true) 状态机**: 显式状态转换 (next_turn, compact_retry, etc.)
- **5层压缩**: tool result budget → snip → microcompact → collapse → auto → reactive
- **流式工具执行**: StreamingToolExecutor 在API流返回时即开始执行工具

### 工具系统 (tools/)
- **buildTool() 工厂模式**: 40+工具通过统一工厂构建
- **并发安全分区**: 自动将工具调用分为并发批(只读)和串行批(写入)
- **7层权限管线**: Zod验证 → hooks → 规则引擎 → 分类器 → 交互确认
- **工具结果大小预算**: 大结果自动持久化到磁盘

### 基础设施
- **MCP**: 6种传输类型 (stdio, SSE, HTTP, WS, SDK, proxy)
- **记忆**: 双系统 — extractMemories (后台fork agent) + SessionMemory (结构化模板)
- **压缩**: 三级 — microcompact + auto-compact + full compaction
- **Bridge**: 环境模式 + 无环境模式，支持多会话

## 📊 与 Hermes Agent 对比

| 维度 | Claude Code | Hermes Agent |
|------|------------|--------------|
| 语言 | TypeScript (Node/Bun) | Python |
| Agent循环 | AsyncGenerator流水线 | 同步循环 |
| 工具系统 | 工厂模式+并发分区 | 类注册 |
| 权限 | 7层管线 | 基础allow/deny |
| 压缩 | 5层自适应 | 简单截断 |
| MCP | 6种传输 | 基础支持 |
| 记忆 | 双系统+后台提取 | 简单注入 |
| 多Agent | Coordinator模式 | delegate_task |

## 🎯 升级方向

详见 `iteration/upgrade-plan.md`

## 来源

- [ChinaSiro/claude-code-sourcemap](https://github.com/ChinaSiro/claude-code-sourcemap) (9.2K ⭐)
- [luyao618/Claude-Code-Source-Study](https://github.com/luyao618/Claude-Code-Source-Study) (1.4K ⭐)
- [anthropics/claude-code](https://github.com/anthropics/claude-code) (126K ⭐) — 官方开源
