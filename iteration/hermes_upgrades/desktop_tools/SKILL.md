---
name: hermes-desktop-pc
description: "Hermes Desktop PC自动化 — 个人PC管理助手：Office文档、邮件收发、数据报表、竞品分析、Web调研、GUI自动化"
category: desktop
---

# Hermes Desktop — 个人 PC 管理助手

让 AI 帮你处理繁琐的办公工作：做 PPT、写报告、收发邮件、数据分析、竞品调研。

## 🇨🇳 中文快速开始

### 第一步：安装依赖

**Linux / macOS:**
```bash
git clone <repo-url> && cd hermes-enhanced/iteration/hermes_upgrades/desktop_tools
bash install.sh
```

**Windows:**
```cmd
cd hermes-enhanced\iteration\hermes_upgrades\desktop_tools
install.bat
```

**或使用 Python 脚本（跨平台）:**
```bash
python setup_deps.py
```

> 💡 安装脚本会自动检测已安装的依赖（openpyxl / python-pptx / python-docx 等），已安装的包会跳过，不会重复安装。

### 第二步：验证安装

```bash
python setup_deps.py --verify-only
```

预期输出：所有项目显示 ✅，如果有 ❌ 按提示修复。

### 第三步：开始使用

安装完成后，在 Hermes Desktop 中直接用自然语言告诉 AI 你想做什么：

```
"帮我做一个 10 页的 Q3 工作汇报 PPT"
"分析这个 Excel 的销售数据，做个报告"
"帮我回复最新那封邮件，语气正式一点"
"做一份 AI Agent 市场的竞品分析报告"
```

### Office 依赖说明

本工具需要以下 Python 库来处理 Office 文档：

| 库 | 用途 | 安装命令 |
|---|---|---|
| `python-docx` | 读写 Word (.docx) | `pip install python-docx` |
| `python-pptx` | 读写 PowerPoint (.pptx) | `pip install python-pptx` |
| `openpyxl` | 读写 Excel (.xlsx) | `pip install openpyxl` |

这些依赖会在安装脚本中自动安装，无需手动操作。

### 常见问题

**Q: 安装太慢？**
- 设置 PyPI 镜像源：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple`
- 或在设置面板 → 网络 → 选择镜像源

**Q: GPU 检测不到？**
- 确认已安装 NVIDIA 驱动：`nvidia-smi`
- 运行 `python setup_deps.py` 查看检测结果

**Q: 邮件发送失败？**
- QQ/163 邮箱需要授权码（非密码），在邮箱设置 → POP3/SMTP 开启

---

## ⚡ 快速安装

```bash
# Linux / macOS
bash install.sh

# Windows
install.bat

# 或 Python 脚本
python setup_deps.py
```

首次启动自动弹出设置向导，引导完成：环境检测 → 网络配置 → 依赖安装。

## 🎯 工作流（一键完成）

### 竞品分析报告
```
"帮我做一份 XX 的竞品分析报告，竞品是 A、B、C"
→ 自动搜索 → 对比分析 → 生成 PPT（含图表/表格）
```

### 周报
```
"帮我写周报：本周完成了 XX 项目、修复了 YY bug、ZZ 方案评审"
→ 整理格式 → 标注状态 → 生成 Word / 发邮件
```

### 会议纪要
```
"整理这段会议记录" [粘贴文字]
→ 提取议题 → 整理决议 → 列出待办 → 生成 Word
```

### 数据分析
```
"分析这个 Excel 的销售数据，做个报告"
→ 读取数据 → 分析趋势 → 生成图表 → 输出 PPT/Excel
```

### 邮件回复
```
"帮我回复最新那封邮件，语气正式一点"
→ 读邮件 → 生成回复 → 直接发送
```

### 搜索调研
```
"调研一下 AI Agent 市场现状"
→ 多角度搜索 → 整理报告 → 生成 Word/PPT
```

### 快速 PPT
```
"做一个 10 页的 Q3 工作汇报 PPT"
→ 搜索数据 → 组织内容 → 套主题 → 生成 PPT
```

## 📄 Office 工具

### Word
- `create_word(path, title, content, template, font_size, line_spacing)` — 创建
- `edit_word(path, operations)` — 编辑（标题/段落/表格/图片/替换/页眉页脚）
- `read_word(path)` — 读取内容

### PPT（增强版）
- `create_ppt(path, slides, template, theme)` — 创建
  - **5 种主题**: business / tech / modern / minimal / nature
  - **9 种页面**: title / content / bullet / two_column / chart / table / section / image / end
  - **图表**: bar / column / line / pie / area
  - **表格**: 自动表头高亮、主题色

### Excel（增强版）
- `create_excel(path, sheets)` — 创建（自动列宽、表头样式）
- `read_excel(path, sheet_name, max_rows)` — 读取
- `edit_excel(path, operations)` — 编辑：
  - set_cell / set_range — 写入数据
  - add_chart — 添加图表（bar/line/pie）
  - add_formula — 添加公式
  - format_cells — 格式化（加粗/颜色/对齐）
  - add_sheet / delete_sheet — 管理工作表
  - auto_filter / merge_cells — 筛选/合并

## ✉️ 邮件工具

### 收邮件
- `read_emails(folder, limit, unread_only, search)` — 邮件列表
- `read_email_detail(uid)` — 邮件全文

### 发邮件
- `send_email(to, subject, body, cc, bcc, html, attachments)` — 发送
- 支持 QQ邮箱/163/Outlook/Gmail/企业邮箱
- 自动检测 IMAP/SMTP 配置

### 配置
首次使用需配置邮箱（设置面板 → 网络 → 邮箱配置），或直接告诉 AI：
```
"配置邮箱：xxx@qq.com，授权码是 yyy"
```

## 🔍 网络调研

- `web_search(query)` — 搜索引擎
- `web_extract(urls)` — 提取网页内容
- 支持代理/镜像源（设置面板配置）

## 🖥️ GUI 自动化

- `screen_capture()` — 截图
- `gui_locate(image, target)` — AI 视觉定位
- `gui_click(x, y)` / `gui_type(text)` / `gui_hotkey(...)` — 操作
- `screen_ocr(image)` — 文字识别

## 📋 系统

- `open_app(name)` — 启动应用
- `get_windows()` — 窗口列表
- `clipboard("get"/"set")` — 剪贴板

## 网络配置

### 代理
- 自动检测 Clash/V2Ray/系统代理
- 手动设置 HTTP/SOCKS5 代理
- 配置持久化

### 镜像源
- HuggingFace: 官方 / hf-mirror.com
- PyPI: 清华 / 阿里云 / 豆瓣 / 中科大

## 故障排除

### PPT/Word/Excel 创建失败
```bash
pip install python-docx python-pptx openpyxl
```

### 邮件发送失败
- QQ邮箱：需要授权码（非密码），在 QQ邮箱 → 设置 → 账户 → POP3 开启
- 163邮箱：需要授权码，在 163邮箱 → 设置 → POP3 开启
- Outlook：可能需要 App Password

### 模型下载慢
设置面板 → 网络 → 选择 hf-mirror 镜像源
