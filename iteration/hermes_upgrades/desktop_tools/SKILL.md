---
name: hermes-desktop-pc
description: "Hermes Desktop PC自动化 — 截图+视觉定位+GUI操作+Office文档。让AI像人一样使用电脑。"
category: desktop
---

# Hermes Desktop PC 自动化

让 Hermes 像人一样操作电脑：看到屏幕 → 理解内容 → 点击/输入/创建文档。

## 核心能力

### 🖥️ 屏幕感知
- `screen_capture()` — 截图
- `gui_locate(image, target)` — AI视觉定位元素
- `screen_ocr(image)` — 文字识别

### 🖱️ GUI 操作
- `gui_click(x, y)` — 点击
- `gui_type(text)` — 输入文字（支持中文）
- `gui_hotkey("ctrl", "s")` — 快捷键
- `gui_scroll(clicks)` — 滚动
- `gui_drag(x1,y1,x2,y2)` — 拖拽

### 📄 Office 文档
- `create_word(path, title, content)` — Word
- `create_ppt(path, slides)` — PPT
- `create_excel(path, sheets)` — Excel
- `edit_word(path, operations)` — 编辑Word

### 📋 系统
- `open_app(name)` — 启动应用
- `get_windows()` — 窗口列表
- `clipboard("get"/"set", text)` — 剪贴板

## 典型工作流

### 创建 PPT
```
1. open_app("powerpoint")
2. gui_locate(screenshot, "空白演示文稿")  → 获取坐标
3. gui_click(x, y)                         → 点击
4. create_ppt("/tmp/ppt.pptx", slides)     → 或用代码直接创建
```

### 填写网页表单
```
1. screen_capture()                        → 截图
2. gui_locate(img, "姓名输入框")           → 定位
3. gui_click(x, y)                         → 点击输入框
4. gui_type("张三")                        → 输入
5. gui_locate(img, "提交按钮")             → 定位按钮
6. gui_click(x, y)                         → 提交
```

### 编辑 Word 文档
```
1. create_word("/tmp/report.docx", "月度报告", "正文内容...")
2. edit_word("/tmp/report.docx", [
     {"type": "add_heading", "text": "第二章", "level": 1},
     {"type": "add_table, "rows": [["项目","进度"],["A","80%"],["B","60%"]]},
   ])
```

## 安全机制
- pyautogui.FAILSAFE = True（鼠标移到左上角紧急停止）
- 所有 GUI 操作前先截图确认
- 危险操作（删除文件、关闭应用）需确认

## 依赖
```
pip install pyautogui pygetwindow pyperclip Pillow python-docx python-pptx openpyxl pytesseract
pip install transformers torch torchvision  # LocateAnything-3B 视觉模型
```
