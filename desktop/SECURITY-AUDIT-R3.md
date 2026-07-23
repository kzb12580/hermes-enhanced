# Hermes Desktop 前端安全审查报告 — 第三轮

**审查模型**: kzb/gemini-3-flash (via mimo-v2.5 subagent)  
**审查时间**: 2026-07-24  
**项目路径**: `/root/hermes-enhanced-latest/desktop`  
**审查范围**: src/ (React组件、stores、hooks、lib)、electron/ (main、preload)、package.json  

---

## 审查摘要

| 级别 | 数量 |
|------|------|
| 🔴 P0 (Critical) | 2 |
| 🟠 P1 (High) | 5 |
| 🟡 P2 (Medium) | 6 |
| **总计** | **13** |

---

## 🔴 P0 — Critical (需立即修复)

### P0-1: `showFatalError()` 中的 XSS 漏洞 — 模板字符串直接注入 HTML

**文件**: `src/main.tsx:15-24`  
**问题**: `showFatalError()` 使用 `root.innerHTML = \`...\${title}...\${detail}\`` 直接将参数插入 HTML 模板字符串，未做任何转义。

- `title` 和 `detail` 来自 `err?.message` 和 `err?.stack`（第59-62行）
- 如果错误消息中包含恶意 HTML/JS（例如来自网络请求的响应被格式化为 Error 对象），攻击者可以注入脚本

**攻击场景**:  
后端 API 返回包含恶意脚本的错误响应 → 错误被封装为 Error 对象 → `bootstrap()` catch 中调用 `showFatalError(err?.message, err?.stack)` → 恶意脚本执行

**修复建议**:
```typescript
function escapeHtml(str: string): string {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

function showFatalError(title: string, detail: string) {
  const root = document.getElementById('root');
  if (root) {
    const safeTitle = escapeHtml(title);
    const safeDetail = escapeHtml(detail);
    root.innerHTML = `...${safeTitle}...${safeDetail}...`;
  }
}
```

**影响**: 在 Electron 渲染进程中，XSS 可以导致任意代码执行（如果 `nodeIntegration` 开启），即使关闭了 `nodeIntegration`，也可以窃取 `localStorage` 中的 API Key 和邮件密码。

---

### P0-2: `sandbox: false` 削弱 Electron 安全模型

**文件**: `electron/main/window.ts:35`  
**问题**: `webPreferences.sandbox` 设为 `false`。注释说明 "sandbox must be false for preload to use Node/Electron APIs"。

虽然 `contextIsolation: true` 和 `nodeIntegration: false` 提供了基本保护，但 `sandbox: false` 意味着：
- Preload 脚本运行在非沙箱环境中，可以访问 Node.js API
- 如果 preload 代码或 `contextBridge.exposeInMainWorld` 存在缺陷，影响面更大
- 不符合 Electron 安全最佳实践（Electron 官方文档明确推荐 `sandbox: true`）

**修复建议**:
- 迁移到 `sandbox: true`，将需要 Node API 的功能移到主进程通过 IPC 处理
- 如果短期无法迁移，至少添加 CSP 头限制渲染进程的网络访问

---

## 🟠 P1 — High (应在下个版本修复)

### P1-1: API Key 和邮箱密码明文持久化在 localStorage

**文件**:  
- `src/stores/settingsStore.ts:183` — `apiKey` 被 `partialize` 到 localStorage
- `src/stores/chatStore.ts:545` — chat history 持久化（含 `activeSkills`）
- `src/components/email/EmailConfig.tsx` — 邮箱密码通过 HTTP 请求发送到后端
- `src/components/email/EmailPanel.tsx:66` — 邮箱配置（含密码）PUT 到后端

**问题**:
1. Zustand `persist` 中间件将 `apiKey`（第183行）直接序列化到 `localStorage('hermes-settings')`
2. 邮箱密码通过明文 JSON 发送到后端 `PUT /api/email/config`
3. localStorage 中的数据未加密，任何具有 DevTools 访问权限的代码都可以读取

**修复建议**:
- 使用 Electron 的 `safeStorage` API 加密敏感字段
- 邮箱密码传输时使用加密通道或专用加密字段
- 考虑使用 `electron-store` 的加密选项替代 localStorage 持久化敏感数据

---

### P1-2: 后端 API 调用使用 HTTP (非 HTTPS) 默认值

**文件**:  
- `src/lib/api.ts:6` — `DEFAULT_BASE_URL = 'http://127.0.0.1:9876'`
- `src/stores/settingsStore.ts:105` — `backendUrl: 'http://127.0.0.1:9876'`

**问题**: 
- 默认后端 URL 使用 HTTP 明文协议
- API Key 通过 `Authorization: Bearer` 头发送（api.ts:111），在 HTTP 连接中可被抓包
- `ChatCompletionRequest.api_key`（第229行）也通过明文 HTTP body 传输

**影响**: 虽然默认绑定 `127.0.0.1`（本地回环），但在以下场景有风险：
- 用户修改 backendUrl 为远程地址
- 同一网络中的恶意软件可以监听本地端口
- 后端配置了 `0.0.0.0` 监听时，局域网内可嗅探

**修复建议**:
- 在后端启用 TLS/HTTPS
- 前端增加协议验证：如果 URL 不以 `https://` 开头，显示安全警告
- 考虑使用 IPC 通道在主进程中处理 API 调用（利用 Electron 的安全网络栈）

---

### P1-3: `fetchModels` 将 API Key 通过明文 HTTP 发送

**文件**: `src/components/models/ModelsPanel.tsx:30`  
**问题**: 
```typescript
const result = await fetchModels(provider.baseUrl, provider.apiKey);
// fetchModels 内部: body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
```
API Key 和 base_url 作为明文 JSON body 发送到后端。如果后端 URL 是 HTTP，API Key 在传输中可被嗅探。

**修复建议**:
- 确保后端 URL 使用 HTTPS
- 或通过 IPC 在主进程中处理模型列表获取

---

### P1-4: 未验证的 JSON.parse 在流处理中

**文件**: `src/stores/chatStore.ts:436, 457`  
**问题**: 
```typescript
const tc = JSON.parse(token.slice(11));  // 第436行
const tr = JSON.parse(token.slice(13));  // 第457行
```
虽然外部有 `try/catch`，但 `JSON.parse` 的结果直接用于构造 `ParsedToolCall` 对象（第438-446行），缺乏字段类型验证。恶意的后端响应可以注入任意结构的数据。

**修复建议**:
```typescript
// 添加 Zod 或简单的运行时验证
if (typeof tc.id !== 'string' || typeof tc.name !== 'string') {
  throw new Error('Invalid tool_call event structure');
}
```

---

### P1-5: `useIpcInvoke` 中的类型不安全转换

**文件**: `src/hooks/useIpc.ts:41-88`  
**问题**: 所有 IPC 调用都使用 `as Promise<T>` 进行强制类型转换：
```typescript
return api.window.minimize() as Promise<T>;
return api.python.start() as Promise<T>;
```
调用者无法在编译时保证类型安全。如果 IPC 响应格式与预期不符，运行时会出现难以调试的错误。

**修复建议**:
- 为每个 IPC 通道定义严格的响应类型
- 在 IPC handler 返回端添加运行时验证

---

## 🟡 P2 — Medium (建议在后续版本改进)

### P2-1: Email 配置密码在测试连接时明文传输

**文件**: `src/components/email/EmailConfig.tsx:210`, `src/components/email/EmailPanel.tsx:79`  
**问题**: `testConnection` 函数将完整的 `config` 对象（包含密码）通过 POST 请求发送到 `/api/email/test`。如果后端 URL 未使用 HTTPS，密码可被嗅探。

**修复建议**: 
- 确保后端支持 HTTPS
- 或在前端发送前加密密码

---

### P2-2: 缺少 CSP (Content-Security-Policy) 头

**文件**: `electron/main/window.ts`  
**问题**: `createMainWindow()` 中没有设置 CSP 头。虽然 `webSecurity: true` 启用了同源策略，但缺少 CSP 限制：
- 无法阻止内联脚本执行
- 无法限制资源加载来源
- 加剧了 P0-1 的 XSS 风险

**修复建议**:
```typescript
mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
  callback({
    responseHeaders: {
      ...details.responseHeaders,
      'Content-Security-Policy': ["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"]
    }
  });
});
```

---

### P2-3: `EmailConfig` 中 `dangerouslySetInnerHTML` 虽经 DOMPurify 但无额外限制

**文件**: `src/components/email/EmailConfig.tsx:330`  
**问题**: 
```tsx
dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(selectedEmail.body_html) }}
```
DOMPurify 的默认配置允许较宽松的 HTML 标签。邮件 HTML 可能包含表单、链接等可交互元素。

**修复建议**:
- 配置更严格的 DOMPurify 选项：
```typescript
DOMPurify.sanitize(html, {
  ALLOWED_TAGS: ['p', 'br', 'b', 'i', 'u', 'em', 'strong', 'a', 'img', 'table', 'tr', 'td', 'th', 'div', 'span', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4'],
  ALLOWED_ATTR: ['href', 'src', 'alt', 'style', 'class'],
  FORBID_TAGS: ['form', 'input', 'button', 'script', 'iframe'],
  FORBID_ATTR: ['onerror', 'onclick', 'onload'],
});
```

---

### P2-4: IPC handler 未验证输入参数类型

**文件**: `electron/main/index.ts:298-309`  
**问题**: 
```typescript
ipcMain.handle(IPC_CHANNELS.SETTINGS_SET, (_event, key: keyof AppSettings, value: AppSettings[typeof key]) => {
  settingsStore.set(key, value)
```
虽然 TypeScript 类型声明了参数类型，但运行时未验证。渲染进程可以发送任意 `key` 和 `value`，绕过类型约束。

**修复建议**:
- 添加运行时验证：检查 `key` 是否在 `AppSettings` 的白名单中
- 验证 `value` 的类型匹配 `key` 对应的预期类型

---

### P2-5: `python-manager.ts` 中 `execAsync` 使用字符串拼接执行命令

**文件**: `electron/main/python-manager.ts:150, 162, 214, 231`  
**问题**: 
```typescript
const pyResult = (await execAsync('py -3 -c "import sys; print(sys.executable)"', { ... })).stdout.trim()
const whereResult = (await execAsync('where python 2>nul', { ... })).stdout.trim()
```
虽然当前使用的是硬编码命令字符串（无用户输入注入），但 `execAsync` 的使用模式不够安全。如果未来有用户可控参数传入，容易产生命令注入。

**修复建议**:
- 优先使用 `spawn` 替代 `exec`
- 如必须使用 `exec`，确保不拼接用户输入
- 添加注释标记这些为 "安全的硬编码命令"

---

### P2-6: `electron-store` 设置文件未加密

**文件**: `electron/main/store.ts`  
**问题**: `electron-store` 将设置持久化为明文 JSON 文件到用户数据目录。虽然不包含 API Key（那是渲染进程 Zustand 管理的），但包含 `pythonPort`、`workspacePath` 等系统配置信息。

**修复建议**:
- 使用 `electron-store` 的加密选项（如果敏感字段增多）
- 确保文件系统权限正确（Electron 默认已经处理）

---

## 已确认的安全优势 ✅

以下方面审查通过，安全实践良好：

1. **Electron 安全配置** — `contextIsolation: true`, `nodeIntegration: false`, `webSecurity: true`
2. **IPC 隔离** — 使用 `contextBridge.exposeInMainWorld` 安全暴露 API
3. **URL 验证** — `isAllowedUrl()` 正确验证外部链接只允许 http/https 协议
4. **SSE 数据解析** — 正确处理 SSE 协议，不 yield 非 SSE 内容（防泄漏）
5. **进程管理** — `buildSafeEnv()` 使用环境变量白名单
6. **Markdown 渲染** — 使用 `rehype-sanitize` 对 AI 响应进行 HTML 清理
7. **邮件 HTML** — 使用 `DOMPurify.sanitize()` 净化邮件 HTML
8. **端口碰撞检测** — `findAvailablePort()` 自动检测可用端口
9. **JSON.parse 保护** — chatStore 中的 JSON.parse 都有 try/catch
10. **session ID 验证** — `switchSession` 验证 session 存在性
11. **URL 编码** — `deleteSession` 和 `getSkill` 正确使用 `encodeURIComponent`

---

## 修复优先级建议

| 优先级 | 问题 | 工作量 |
|--------|------|--------|
| 🔴 立即 | P0-1: showFatalError XSS | 小 (1小时) |
| 🔴 立即 | P0-2: sandbox: false | 大 (需重构 preload) |
| 🟠 下版本 | P1-1: 密钥明文持久化 | 中 (引入 safeStorage) |
| 🟠 下版本 | P1-2: HTTP 默认值 | 小 (加协议检查) |
| 🟠 下版本 | P1-3: fetchModels API Key | 小 (同 P1-2) |
| 🟠 下版本 | P1-4: JSON.parse 类型验证 | 小 (加 Zod schema) |
| 🟠 下版本 | P1-5: IPC 类型安全 | 中 |
| 🟡 后续 | P2-1 ~ P2-6 | 各 0.5-2 小时 |

---

**审查结论**: 项目整体安全实践良好，Electron 安全配置规范，IPC 隔离到位。主要风险集中在 **XSS 注入**（P0-1）和 **敏感数据明文存储**（P1-1）。建议优先修复 P0-1（1小时工作量即可完成），P1-1 在下个版本引入加密存储。P0-2（sandbox）属于架构级改动，建议纳入技术债务跟踪。
