---
name: image-processing
description: "图片处理 — 裁剪、缩放、滤镜、格式转换、水印、拼图"
category: office
version: "1.0"
tags: [image, processing, resize, crop, filter, watermark]
---

# 图片处理技能

## 工具依赖
- Python: Pillow (PIL)

## 安装
```bash
pip install Pillow
```

## 常用操作

### 1. 裁剪图片
```python
from PIL import Image

img = Image.open('input.png')
# (left, top, right, bottom)
cropped = img.crop((100, 100, 500, 400))
cropped.save('cropped.png')
```

### 2. 缩放图片
```python
from PIL import Image

img = Image.open('input.png')
# 按尺寸缩放
resized = img.resize((800, 600))
# 按比例缩放
w, h = img.size
resized = img.resize((w // 2, h // 2))
resized.save('resized.png')
```

### 3. 旋转/翻转
```python
from PIL import Image

img = Image.open('input.png')
rotated = img.rotate(90, expand=True)  # 顺时针90度
flipped = img.transpose(Image.FLIP_LEFT_RIGHT)  # 水平翻转
flipped = img.transpose(Image.FLIP_TOP_BOTTOM)  # 垂直翻转
```

### 4. 添加水印
```python
from PIL import Image, ImageDraw, ImageFont

img = Image.open('input.png').convert('RGBA')
overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

font = ImageFont.truetype('arial.ttf', 36)
draw.text((50, 50), '水印文字', fill=(255, 255, 255, 128), font=font)

watermarked = Image.alpha_composite(img, overlay).convert('RGB')
watermarked.save('watermarked.png')
```

### 5. 格式转换
```python
from PIL import Image

img = Image.open('input.png')
img.save('output.jpg', 'JPEG', quality=95)
img.save('output.webp', 'WebP', quality=90)
img.save('output.bmp')
```

### 6. 图片拼接
```python
from PIL import Image

imgs = [Image.open(f'img{i}.png') for i in range(4)]
# 横向拼接
total_w = sum(img.width for img in imgs)
max_h = max(img.height for img in imgs)
result = Image.new('RGB', (total_w, max_h))
x = 0
for img in imgs:
    result.paste(img, (x, 0))
    x += img.width
result.save('combined.png')
```

### 7. 应用滤镜
```python
from PIL import Image, ImageFilter

img = Image.open('input.png')
blurred = img.filter(ImageFilter.BLUR)
sharpened = img.filter(ImageFilter.SHARPEN)
edges = img.filter(ImageFilter.FIND_EDGES)
grayscale = img.convert('L')
```

### 8. 调整亮度/对比度
```python
from PIL import Image, ImageEnhance

img = Image.open('input.png')
bright = ImageEnhance.Brightness(img).enhance(1.5)  # 1.5倍亮度
contrast = ImageEnhance.Contrast(img).enhance(1.2)  # 1.2倍对比度
sharp = ImageEnhance.Sharpness(img).enhance(2.0)  # 2倍锐化
```

### 9. 批量处理
```python
from PIL import Image
import os

input_dir = 'photos/'
output_dir = 'processed/'
os.makedirs(output_dir, exist_ok=True)

for f in os.listdir(input_dir):
    if f.endswith(('.png', '.jpg', '.jpeg')):
        img = Image.open(os.path.join(input_dir, f))
        img.thumbnail((800, 800))  # 保持比例缩放到800px以内
        img.save(os.path.join(output_dir, f), quality=85)
```

## 注意事项
- 保存为 JPEG 时需转为 RGB 模式（去掉 alpha 通道）
- `thumbnail()` 保持比例，`resize()` 强制尺寸
- 大批量处理建议用 `os.path` 遍历
