# Hermes Desktop PC 自动化 — 使用指南

## 🚀 安装步骤（Windows PC）

### 第 1 步：克隆仓库
```cmd
git clone https://github.com/kzb12580/hermes-enhanced.git
cd hermes-enhanced\iteration\hermes_upgrades\desktop_tools
```

### 第 2 步：安装依赖
```cmd
pip install pyautogui pygetwindow pyperclip Pillow python-docx python-pptx openpyxl pytesseract opencv-python-headless
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install transformers peft
```

### 第 3 步：下载视觉模型（约 6GB）
```cmd
python -c "from transformers import AutoModelForCausalLM, AutoProcessor; AutoProcessor.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True); AutoModelForCausalLM.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True); print('Done!')"
```

### 第 4 步：在 Hermes Desktop 设置中启用

打开 Hermes Desktop → 设置 → 工具管理：

```
┌─────────────────────────────────────────────────┐
│  ◆ 工具管理                                      │
│                                                  │
│  ☑ 终端命令        ☑ 文件操作     ☑ 网络搜索     │
│  ☑ 浏览器操作      ☑ 剪贴板       ☑ 截图         │
│                                                  │
│  ── PC 自动化（新增）──                           │
│  ☑ GUI 操作        鼠标点击/输入/拖拽             │
│  ☑ 视觉定位        AI识别屏幕元素                 │
│  ☑ Office 文档     Word/PPT/Excel                │
│  ☑ OCR 识别        图片文字识别                   │
│                                                  │
│  ── 视觉模型 ──                                   │
│  模型路径: [nvidia/LocateAnything-3B    ]         │
│  设备:     [CUDA (GPU)          ▼]               │
│  推理模式: [hybrid (推荐)       ▼]               │
│  ☑ 启动时预加载模型                               │
│                                                  │
│  [测试连接]  [保存]                               │
└─────────────────────────────────────────────────┘
```

## 🎯 使用方法

### 方式 1：直接对话（推荐）
在 Hermes Desktop 聊天框中直接说：

```
"帮我截个屏，看看桌面上有什么"
"帮我打开 Word，写一份项目周报"
"帮我做一个关于AI趋势的PPT，5页"
"帮我点击左上角的文件菜单"
"帮我把这个网页的表格复制到Excel"
```

### 方式 2：组合工作流
```
"帮我做一份月度销售报告PPT：
 1. 先截图当前的Excel数据
 2. 用OCR识别数据内容
 3. 创建PPT，每页一个图表
 4. 保存到桌面"
```

### 方式 3：技能指令
```
/screen_capture                    → 截图
/gui_locate "保存按钮"             → 定位元素
/gui_click 500 300                 → 点击坐标
/gui_type "你好世界"               → 输入文字
/gui_hotkey ctrl s                 → 快捷键
/create_word report.docx "标题"    → 创建Word
/create_ppt slides.pptx [...]      → 创建PPT
/open_app word                     → 打开Word
```

## ⚡ 快捷操作

| 你说的话 | Hermes 做的事 |
|---------|--------------|
| "截屏" | 截图并显示 |
| "点击XX" | 视觉定位+点击 |
| "输入XX" | 定位输入框+输入 |
| "做个PPT" | 创建PPT文件 |
| "写个文档" | 创建Word文件 |
| "打开XX" | 启动应用 |
| "保存" | Ctrl+S |
| "复制这个" | Ctrl+C |

## 🔧 配置文件

设置保存在 Hermes Desktop 配置中：

```yaml
# ~/.hermes/desktop-tools.yaml
desktop_tools:
  enabled: true
  
  vision:
    model: "nvidia/LocateAnything-3B"
    device: "cuda"
    mode: "hybrid"        # fast/slow/hybrid
    preload: false         # 启动时预加载（占用~6GB显存）
    auto_unload: true      # 空闲30分钟后自动释放显存
    
  gui:
    failsafe: true         # 鼠标移到左上角紧急停止
    pause: 0.05            # 每次操作后暂停(ms)
    coordinate_verify: true # 点击前验证坐标范围
    
  office:
    max_content_mb: 10     # 最大文档大小
    max_rows: 100000       # Excel最大行数
    default_template: ""   # 默认模板路径
```

## ⚠️ 安全提示

1. **FAILSAFE**: 鼠标移到屏幕左上角会紧急停止所有操作
2. **截图确认**: 每次操作前会先截图确认当前状态
3. **危险操作**: 删除文件、关闭应用前会弹窗确认
4. **路径安全**: 所有文件操作都限制在安全目录内

## 🐛 常见问题

**Q: 模型加载很慢？**
A: 首次加载约需 10-30 秒。设置 `preload: true` 可启动时预加载。

**Q: 中文输入不生效？**
A: 工具会自动通过剪贴板粘贴，确保目标窗口支持粘贴。

**Q: 点击偏移？**
A: 检查是否有缩放（DPI），Windows 显示缩放建议设为 100%。

**Q: 显存不够？**
A: LocateAnything-3B 需要约 6GB VRAM。设置 `auto_unload: true` 空闲时自动释放。

**Q: 支持多显示器？**
A: 支持。坐标是全屏绝对坐标，(0,0) 是主显示器左上角。
