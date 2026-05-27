---
name: pdf-processing
description: "PDF 处理 — 合并、拆分、提取文字/图片、加密、压缩"
category: office
version: "1.0"
tags: [pdf, merge, split, extract, encrypt]
---

# PDF 处理技能

## 工具依赖
- Python: PyPDF2, pdfplumber, Pillow

## 安装
```bash
pip install PyPDF2 pdfplumber Pillow
```

## 常用操作

### 1. 合并 PDF
```python
from PyPDF2 import PdfMerger

merger = PdfMerger()
for pdf in ['file1.pdf', 'file2.pdf', 'file3.pdf']:
    merger.append(pdf)
merger.write('merged.pdf')
merger.close()
```

### 2. 拆分 PDF
```python
from PyPDF2 import PdfReader, PdfWriter

reader = PdfReader('input.pdf')
# 每页一个文件
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f'page_{i+1}.pdf', 'wb') as f:
        writer.write(f)

# 提取指定页
writer = PdfWriter()
writer.add_page(reader.pages[0])  # 第1页
writer.add_page(reader.pages[2])  # 第3页
with open('extracted.pdf', 'wb') as f:
    writer.write(f)
```

### 3. 提取文字
```python
import pdfplumber

with pdfplumber.open('input.pdf') as pdf:
    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        print(f'--- Page {i+1} ---')
        print(text)
```

### 4. 提取图片
```python
from PyPDF2 import PdfReader

reader = PdfReader('input.pdf')
for i, page in enumerate(reader.pages):
    for j, img in enumerate(page.images):
        with open(f'page{i+1}_img{j+1}.png', 'wb') as f:
            f.write(img.data)
```

### 5. 添加密码
```python
from PyPDF2 import PdfReader, PdfWriter

reader = PdfReader('input.pdf')
writer = PdfWriter()
for page in reader.pages:
    writer.add_page(page)
writer.encrypt('mypassword')
with open('encrypted.pdf', 'wb') as f:
    writer.write(f)
```

### 6. 旋转页面
```python
from PyPDF2 import PdfReader, PdfWriter

reader = PdfReader('input.pdf')
writer = PdfWriter()
for page in reader.pages:
    page.rotate(90)  # 顺时针90度
    writer.add_page(page)
with open('rotated.pdf', 'wb') as f:
    writer.write(f)
```

## 注意事项
- pdfplumber 提取文字比 PyPDF2 更准确
- 加密后的 PDF 需要密码才能打开
- 大文件建议分批处理
