---
name: data-analysis
description: |
  数据分析专家 — CSV、JSON 数据的统计分析与可视化。
category: data
tags:
  - data
  - analysis
  - statistics
  - csv
  - json
  - pandas
triggers:
  - 数据
  - 分析
  - 统计
  - CSV
  - JSON
  - 数据分析
  - 可视化
  - 图表
  - 汇总
  - 平均值
tools:
  - read_file
  - terminal
  - write_file
priority: 7
---

# 数据分析专家

## 功能说明
对结构化数据（CSV、JSON、日志等）进行统计分析、
聚合计算、趋势识别和数据可视化。支持使用 Python
(pandas/numpy) 或命令行工具处理数据。

## 使用场景
- 分析 CSV 文件中的数据分布和统计指标
- 对 JSON 数据进行聚合和筛选
- 生成数据报告和摘要
- 识别数据中的异常值和趋势
- 数据格式转换和清洗

## 工作流程
1. 使用 `read_file` 查看数据文件的结构和样本
2. 使用 `terminal` 运行 Python 脚本或命令行工具进行分析
3. 使用 `write_file` 保存分析结果或生成报告

## 常用分析脚本
```python
# Python pandas 分析示例
import pandas as pd

df = pd.read_csv('data.csv')
print(df.describe())              # 基本统计
print(df.info())                  # 数据类型和空值
print(df.corr())                  # 相关性矩阵
print(df.groupby('col').mean())   # 分组平均值
print(df.nlargest(10, 'value'))   # 前 10 大值
```

```bash
# 命令行快速分析
# CSV 列统计
awk -F',' '{sum+=$2; count++} END {print "avg:", sum/count}' data.csv

# 唯一值计数
cut -d',' -f1 data.csv | sort | uniq -c | sort -rn

# CSV 行数
wc -l data.csv

# 快速查看前几行
head -5 data.csv

# CSV 转 JSON
python3 -c "import csv,json; data=list(csv.DictReader(open('data.csv'))); print(json.dumps(data, indent=2))"
```

## 分析维度
- **描述性统计**: 均值、中位数、标准差、分位数
- **分布分析**: 频率分布、直方图数据
- **趋势分析**: 时间序列变化
- **异常检测**: 离群值识别
- **相关性**: 变量间关联关系
