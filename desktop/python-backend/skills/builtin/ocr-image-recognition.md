---
name: ocr-image-recognition
description: "OCR 图像文字识别 — 从图片、截图、PDF 中提取文字"
category: office
version: "1.0"
tags: [ocr, image, text-recognition, office]
---

# OCR 图像文字识别

## 功能
从图片、截图、扫描件、PDF 中提取文字内容。

## 工具依赖
- Python: pytesseract, Pillow, pdf2image
- 系统: tesseract-ocr

## 步骤

### 1. 安装依赖
```bash
pip install pytesseract Pillow pdf2image
# Ubuntu/Debian
sudo apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
# macOS
brew install tesseract tesseract-lang
# Windows: 下载安装 https://github.com/UB-Mannheim/tesseract/wiki
```

### 2. 基本用法
```python
from PIL import Image
import pytesseract

# 识别单张图片
text = pytesseract.image_to_string(Image.open('image.png'), lang='chi_sim+eng')
print(text)
```

### 3. 识别截图
```python
from PIL import ImageGrab
import pytesseract

# 截取屏幕
screenshot = ImageGrab.grab()
text = pytesseract.image_to_string(screenshot, lang='chi_sim+eng')
```

### 4. 识别 PDF
```python
from pdf2image import convert_from_path
import pytesseract

pages = convert_from_path('document.pdf', 300)
for i, page in enumerate(pages):
    text = pytesseract.image_to_string(page, lang='chi_sim+eng')
    print(f'--- Page {i+1} ---')
    print(text)
```

### 5. 带坐标的识别（用于定位）
```python
import pytesseract
from pytesseract import Output

data = pytesseract.image_to_data(Image.open('image.png'), output_type=Output.DICT)
for i, word in enumerate(data['text']):
    if word.strip():
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        print(f'{word} @ ({x},{y}) {w}x{h}')
```

## 语言代码
- `chi_sim`: 简体中文
- `chi_tra`: 繁体中文
- `eng`: 英语
- `jpn`: 日语
- `kor`: 韩语

## 注意事项
- 图片分辨率越高，识别越准确
- 建议 300 DPI 以上
- 混合语言用 `+` 连接：`chi_sim+eng`
