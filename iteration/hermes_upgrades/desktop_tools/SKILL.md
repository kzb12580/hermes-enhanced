---
name: hermes-desktop-pc
description: "Hermes Desktop PC自动化 — 个人PC管理助手：Office文档、邮件收发、数据报表、竞品分析、Web调研、GUI自动化"
category: desktop
---

# Hermes Desktop — 个人 PC 管理助手

让 AI 帮你处理繁琐的办公工作：做 PPT、写报告、收发邮件、数据分析、竞品调研。

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
