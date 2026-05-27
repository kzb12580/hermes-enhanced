---
name: file-manager
description: |
  文件管理专家 — 查找、整理、清理和批量操作文件与目录。
category: productivity
tags:
  - file
  - directory
  - filesystem
  - organize
  - cleanup
triggers:
  - 文件
  - 批量
  - 查找
  - 整理
  - 清理
  - 查看
  - 目录
  - 文件夹
  - 重命名
  - 移动
  - 复制
  - 删除文件
tools:
  - read_file
  - write_file
  - search_files
  - terminal
priority: 8
---

# 文件管理专家

## 功能说明
全面的文件与目录管理能力，涵盖查找、整理、清理、批量重命名、
目录树查看、磁盘占用分析等常用操作。支持按名称、大小、时间
和内容进行筛选，帮助用户高效管理本地文件系统。

## 使用场景
- 查找某个目录下的特定类型文件
- 按规则批量重命名文件
- 清理临时文件或重复文件
- 查看目录结构和磁盘占用
- 移动、复制、删除文件或目录
- 按文件大小/日期排序和筛选

## 工作流程
1. 使用 `search_files` 定位目标文件或目录
2. 使用 `read_file` 查看文件内容（如需确认）
3. 使用 `terminal` 执行文件操作命令（mv, cp, rm, find 等）
4. 使用 `write_file` 创建整理报告或脚本

## 常用命令参考
```bash
# 查找大于 100MB 的文件
find /path -type f -size +100M -exec ls -lh {} \;

# 按扩展名统计文件数量
find . -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn

# 批量重命名（去掉空格）
for f in *\ *; do mv "$f" "${f// /_}"; done

# 查看目录树（限深度 3 层）
tree -L 3 -h --du

# 查找最近 7 天修改的文件
find . -type f -mtime -7 -ls

# 清理 __pycache__ 目录
find . -type d -name __pycache__ -exec rm -rf {} +

# 查找重复文件（基于 MD5）
find . -type f -exec md5sum {} + | sort | uniq -d -w32
```

## 注意事项
- 删除操作前建议先用 `-print` 或 `ls` 确认目标
- 大批量操作建议先在小范围测试
- 涉及系统目录时需格外谨慎
