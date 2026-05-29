---
name: hermes-desktop-pc
description: "Hermes Desktop PC自动化 — 截图+视觉定位+GUI操作+Office文档。让AI像人一样使用电脑。"
category: desktop
---

# Hermes Desktop PC 自动化

让 Hermes 像人一样操作电脑：看到屏幕 → 理解内容 → 点击/输入/创建文档。

## ⚡ 快速安装

### 一键安装（推荐）

```bash
# Linux / macOS
bash install.sh

# Windows (CMD)
install.bat

# 或用 Python 脚本（最灵活）
python setup_deps.py
```

安装脚本会自动：
- ✅ 检测 Python 版本（>= 3.10）
- ✅ 检测 NVIDIA GPU / CUDA 版本
- ✅ 安装 PyTorch（自动匹配 CUDA 11.8/12.4/CPU）
- ✅ 安装所有 Python 依赖
- ✅ 安装 Tesseract OCR + 中文语言包
- ✅ 下载 LocateAnything-3B 模型（~6GB）
- ✅ 验证所有组件

### 安装选项

```bash
python setup_deps.py --verify-only    # 仅验证，不安装
python setup_deps.py --skip-model     # 跳过模型下载
python setup_deps.py --skip-tesseract # 跳过 OCR
python setup_deps.py --force-model    # 强制重新下载模型
```

### 依赖清单

| 组件 | 用途 | 自动安装 |
|------|------|---------|
| Python >= 3.10 | 运行环境 | ✅ |
| PyTorch | 深度学习框架 | ✅ (自动匹配CUDA) |
| transformers | 模型加载 | ✅ |
| LocateAnything-3B | 视觉定位模型 | ✅ (~6GB) |
| pyautogui | GUI操作 | ✅ |
| Pillow | 图像处理 | ✅ |
| python-docx/pptx/xlsx | Office文档 | ✅ |
| Tesseract OCR | 文字识别 | ✅ (Linux/macOS) |

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

### 填写网页表单
```
1. screen_capture()                        → 截图
2. gui_locate(img, "姓名输入框")           → 定位
3. gui_click(x, y)                         → 点击输入框
4. gui_type("张三")                        → 输入
5. gui_locate(img, "提交按钮")             → 定位按钮
6. gui_click(x, y)                         → 提交
```

### 创建 PPT
```
1. open_app("powerpoint")
2. gui_locate(screenshot, "空白演示文稿")  → 获取坐标
3. gui_click(x, y)                         → 点击
4. create_ppt("/tmp/ppt.pptx", slides)     → 或用代码直接创建
```

## 故障排除

### 模型加载失败
```bash
# 检查依赖
python setup_deps.py --verify-only

# 重新下载模型
python setup_deps.py --force-model
```

### CUDA 内存不足
- LocateAnything-3B 需要 ~6GB VRAM
- 自动切换为 CPU 模式（较慢但可用）
- 关闭其他 GPU 应用释放显存

### Tesseract 找不到
```bash
# Linux
sudo apt install tesseract-ocr tesseract-ocr-chi-sim

# macOS
brew install tesseract tesseract-lang

# Windows: 下载安装包
# https://github.com/UB-Mannheim/tesseract/wiki
```

## 安全机制
- pyautogui.FAILSAFE = True（鼠标移到左上角紧急停止）
- 所有路径经过净化验证
- shell 命令参数经过列表传递（无注入风险）
- 坐标范围验证（防止 NaN/Inf/越界）
