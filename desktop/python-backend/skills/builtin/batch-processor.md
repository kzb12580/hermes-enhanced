---
name: batch-processor
description: |
  批量处理专家 — 多文件批量操作和循环处理。
category: productivity
tags:
  - batch
  - bulk
  - loop
  - multi-file
  - automation
triggers:
  - 批量
  - 批处理
  - 多文件
  - 循环
  - 自动化
  - 批量处理
  - 循环处理
  - 多个文件
tools:
  - terminal
  - read_file
  - write_file
priority: 6
---

# 批量处理专家

## 功能说明
帮助用户对多个文件或数据项执行批量操作，包括
批量重命名、批量转换、批量编辑和批量分析等。
支持 shell 循环、xargs、parallel 等多种批处理方式。

## 使用场景
- 批量重命名文件
- 批量转换文件格式
- 批量搜索和替换
- 批量处理图片/视频
- 批量数据导入导出

## 工作流程
1. 分析批量处理需求
2. 使用 `terminal` 编写批处理脚本
3. 先在小范围测试
4. 确认无误后执行全部

## 常用批处理模式
```bash
# --- for 循环 ---
# 批量重命名
for f in *.txt; do
    mv "$f" "${f%.txt}.md"
done

# 批量转换编码
for f in *.csv; do
    iconv -f GBK -t UTF-8 "$f" -o "utf8_$f"
done

# 批量压缩图片
for f in *.png; do
    convert "$f" -quality 85 "compressed_$f"
done

# --- find + exec ---
# 批量修改权限
find . -type f -name "*.sh" -exec chmod +x {} \;

# 批量删除临时文件
find . -name "*.tmp" -exec rm {} \;

# --- xargs ---
# 批量搜索
find . -name "*.py" | xargs grep -l "import os"

# 并行处理
find . -name "*.jpg" | xargs -P 4 -I {} convert {} -resize 50% small_{}

# --- parallel ---
# 并行执行命令
cat urls.txt | parallel -j 4 curl -s {} -o {.}.html
```

## Python 批处理脚本
```python
import os
import glob
from pathlib import Path

# 批量处理文件
for file_path in Path('.').glob('*.csv'):
    # 读取、处理、保存
    with open(file_path) as f:
        content = f.read()
    # 处理逻辑
    processed = content.upper()
    with open(f'processed_{file_path.name}', 'w') as f:
        f.write(processed)

# 使用 ThreadPoolExecutor 并行处理
from concurrent.futures import ThreadPoolExecutor

def process_file(path):
    # 处理单个文件
    pass

files = list(Path('.').glob('*.dat'))
with ThreadPoolExecutor(max_workers=4) as executor:
    executor.map(process_file, files)
```

## 安全提示
- 批量删除前先用 `echo` 或 `ls` 预览
- 大批量操作先在小样本测试
- 使用 `-i` 参数交互确认
- 备份重要文件
