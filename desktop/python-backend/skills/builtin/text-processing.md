---
name: text-processing
description: |
  文本处理专家 — 文本替换、格式转换、清洗和变换。
category: productivity
tags:
  - text
  - replace
  - format
  - transform
  - sed
  - awk
triggers:
  - 文本
  - 替换
  - 格式
  - 转换
  - 清理
  - 文本处理
  - 字符串
  - 格式化
  - 去重
  - 排序
tools:
  - read_file
  - write_file
  - terminal
priority: 7
---

# 文本处理专家

## 功能说明
提供全面的文本处理能力，包括批量替换、格式转换、
行操作（排序、去重、筛选）、编码转换、空白处理等。
支持处理单个文件或批量处理多个文件。

## 使用场景
- 批量替换文件中的字符串
- 将文本文件转换为不同格式
- 清理多余空白行或空格
- 对文件内容进行排序或去重
- CSV/TSV 等分隔符格式转换
- 文本编码转换（UTF-8, GBK, Latin-1 等）

## 工作流程
1. 使用 `read_file` 查看源文件内容
2. 使用 `terminal` 执行文本处理命令
3. 使用 `write_file` 保存处理结果
4. 验证输出是否符合预期

## 常用命令参考
```bash
# 批量替换文件中的字符串
sed -i 's/old/new/g' file.txt

# 删除空行
sed -i '/^$/d' file.txt

# 排序并去重
sort -u input.txt -o output.txt

# 提取特定列
awk -F',' '{print $2}' data.csv

# 统计行数/单词数/字符数
wc -l -w -c file.txt

# 转换编码
iconv -f GBK -t UTF-8 input.txt -o output.txt

# 合并多个文件
cat file1.txt file2.txt > merged.txt

# 提取匹配行
grep -E "pattern" file.txt

# 去除行首尾空白
sed 's/^[[:space:]]*//;s/[[:space:]]*$//' file.txt

# 将多行合并为一行
paste -sd ',' file.txt
```

## 高级用法
```bash
# 使用 awk 进行复杂文本处理
awk 'BEGIN{FS=","; OFS="\t"} {print $1, $3, $5}' data.csv

# 使用 sed 进行多行替换
sed -N '1,5{s/old/new/g;P}' file.txt

# 使用 perl 进行正则替换（支持非贪婪匹配）
perl -pe 's/pattern/replacement/g' file.txt
```
