# Hermes Agent 升级方案

> 参考 Claude Code 源码架构，迭代升级 Hermes Agent

## 一、架构升级优先级

### P0 - 核心改进（立即可做）

#### 1. 工具并发分区
**现状**: Hermes Agent 工具串行执行
**目标**: 参考 Claude Code 的并发安全分区算法
- 只读工具 (read_file, search_files, web_search) 自动并发
- 写入工具 (write_file, patch, terminal) 串行执行
- 最大并发数限制 (建议5)

**实现方案**:
```python
# 在 agent loop 中加入工具分类和并发调度
TOOL_CONCURRENCY = {
    'read_file': 'concurrent',
    'search_files': 'concurrent',
    'web_search': 'concurrent',
    'web_extract': 'concurrent',
    'write_file': 'serial',
    'patch': 'serial',
    'terminal': 'serial',
}
```

#### 2. 工具结果大小管理
**现状**: 工具结果直接注入上下文，容易爆
**目标**: 参考 Claude Code 的大小预算 + 磁盘持久化
- 工具结果超过阈值自动截断 + 写入临时文件
- 摘要注入上下文，完整结果按需读取

#### 3. 上下文压缩改进
**现状**: 简单的消息截断
**目标**: 三级压缩
- Level 1: 清理旧的工具结果 (保留最近N轮)
- Level 2: 压缩长对话历史为摘要
- Level 3: 全量压缩 (fork agent总结)

### P1 - 中期改进

#### 4. 权限管线增强
**现状**: 基础 allow/deny
**目标**: 分层权限
- 预执行 hooks (用户自定义规则)
- 工具级权限检查
- 危险操作确认
- 后执行 hooks

#### 5. MCP 传输层增强
**现状**: 基础 stdio 支持
**目标**: 支持更多传输
- SSE (Server-Sent Events)
- HTTP (Streamable HTTP)
- WebSocket
- OAuth 认证

#### 6. 记忆系统增强
**现状**: 简单文本注入
**目标**: 双系统
- 持久记忆: 结构化存储，分类检索
- 会话记忆: 模板化会话总结
- 后台提取: fork agent 自动提取关键信息

### P2 - 长期改进

#### 7. AsyncGenerator 流水线
**现状**: 同步循环
**目标**: 异步生成器管道 (需要较大重构)
- 流式工具执行
- 背压控制
- 取消传播

#### 8. Coordinator 多Agent模式
**现状**: delegate_task 简单分发
**目标**: 协调器模式
- Worker 生成和管理
- 任务通知 (XML格式)
- 合成 prompt
- 结果聚合

## 二、可直接复用的代码模式

### 1. buildTool() 工厂模式
参考 `src/tools/shared/buildTool.ts`
```typescript
// Claude Code 的工具工厂 - 我们可以移植到 Python
const tool = buildTool({
  name: 'bash',
  description: '...',
  inputSchema: z.object({ command: z.string() }),
  isEnabled: () => true,
  checkPermissions: async (input, ctx) => { ... },
  call: async (input, ctx) => { ... },
  // 40+ optional methods with sensible defaults
})
```

**Python 等价**:
```python
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    is_enabled: Callable = lambda: True
    check_permissions: Callable = None
    execute: Callable = None
    # ... defaults for all optional methods
```

### 2. 文件过时检测
参考 `src/tools/shared/fileStaleness.ts`
- 检查文件时间戳 + 内容哈希
- 防止基于过时内容的编辑

### 3. 工具搜索/延迟加载
参考 `src/tools/ToolSearchTool/`
- 工具太多时，不全量注入
- 按需搜索相关工具
- 减少 token 消耗

## 三、测试计划

### 测试服务器
- **kou-amd** (129.151.29.177): ECH/DOH服务器，可用于网络功能测试
- **Oracle 161.153.82.31**: 测试服务器，已部署 v2ray-agent

### 测试内容
1. 工具并发分区 - 构造并发场景验证
2. 上下文压缩 - 长对话压力测试
3. MCP 传输 - 连接不同 MCP 服务器
4. 记忆系统 - 持久记忆读写验证

## 四、时间线

- **Week 1**: P0 核心改进 (并发分区 + 结果管理 + 压缩)
- **Week 2**: P1 中期改进 (权限 + MCP + 记忆)
- **Week 3-4**: P2 长期改进 (流式 + Coordinator)
- **持续**: 测试验证 + 代码审查
