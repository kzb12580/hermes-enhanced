---
name: csv-handler
description: |
  CSV 处理专家 — CSV 文件的读取、处理和转换。
category: data
tags:
  - csv
  - table
  - data
  - spreadsheet
  - tsv
triggers:
  - csv
  - 表格
  - 数据
  - 导入导出
  - CSV
  - TSV
  - 电子表格
  - Excel
tools:
  - read_file
  - terminal
  - write_file
priority: 6
---

# CSV 处理专家

## 功能说明
全面的 CSV 文件处理能力，包括读取、筛选、排序、
合并、拆分、格式转换和数据清洗。支持处理大型 CSV
文件和各种分隔符格式。

## 使用场景
- 读取和分析 CSV 数据
- 筛选和排序 CSV 行
- 合并多个 CSV 文件
- CSV 格式转换（分隔符、编码）
- CSV 与 JSON/Excel 互转
- 数据清洗和去重

## 工作流程
1. 使用 `read_file` 查看 CSV 文件头部和结构
2. 使用 `terminal` 执行 CSV 处理命令
3. 使用 `write_file` 保存处理结果

## 常用命令
```bash
# --- 基础操作 ---
head -5 data.csv                     # 查看前 5 行
wc -l data.csv                       # 行数统计
cut -d',' -f1,3 data.csv             # 提取第 1,3 列

# --- 筛选 ---
awk -F',' '$3 > 100' data.csv        # 第 3 列大于 100 的行
grep "pattern" data.csv              # 搜索匹配行

# --- 排序 ---
sort -t',' -k2 -n data.csv           # 按第 2 列数值排序
sort -t',' -k2 -r data.csv           # 逆序

# --- 去重 ---
awk -F',' '!seen[$1]++' data.csv     # 按第 1 列去重
sort -t',' -k1 -u data.csv           # 排序去重

# --- 合并 ---
cat file1.csv file2.csv > merged.csv # 简单合并
# 去掉重复 header
head -1 file1.csv > merged.csv && tail -n +2 file1.csv file2.csv >> merged.csv

# --- 统计 ---
awk -F',' '{sum+=$2} END {print sum/NR}' data.csv  # 平均值
awk -F',' 'NR==1||$2>max{max=$2} END {print max}' data.csv  # 最大值
```

## Python CSV 处理
```python
import csv
import pandas as pd

# 读取 CSV
df = pd.read_csv('data.csv', encoding='utf-8')

# 筛选
filtered = df[df['age'] > 18]

# 排序
sorted_df = df.sort_values('name', ascending=False)

# 分组统计
grouped = df.groupby('category').agg({'value': ['mean', 'sum', 'count']})

# 保存
df.to_csv('output.csv', index=False, encoding='utf-8-sig')

# CSV 转 JSON
import json
data = df.to_dict('records')
with open('output.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
```

## 编码处理
```bash
# 检测编码
file -i data.csv

# 转换编码
iconv -f GBK -t UTF-8 data.csv -o data_utf8.csv

# Python 处理编码
python3 -c "import pandas as pd; pd.read_csv('data.csv', encoding='gbk').to_csv('out.csv', index=False, encoding='utf-8-sig')"
```
