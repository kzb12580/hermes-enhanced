---
name: json-processor
description: |
  JSON 处理专家 — JSON 数据的解析、转换和格式化。
category: data
tags:
  - json
  - parse
  - format
  - transform
  - jq
triggers:
  - json
  - 解析
  - 格式化
  - 转换
  - JSON
  - 数据格式
  - JSONL
  - NDJSON
tools:
  - read_file
  - write_file
  - terminal
priority: 6
---

# JSON 处理专家

## 功能说明
全面的 JSON 数据处理能力，包括格式化、压缩、
查询提取、结构转换、验证和 JSON Lines 处理。
支持 jq、Python json 模块等多种工具。

## 使用场景
- 格式化压缩的 JSON 数据
- 从大型 JSON 中提取特定字段
- JSON 结构转换和映射
- JSON 数据验证
- JSON 与其他格式（CSV、YAML）互转
- 处理 JSON Lines / NDJSON 格式

## 工作流程
1. 使用 `read_file` 查看 JSON 文件内容
2. 使用 `terminal` 执行 JSON 处理命令
3. 使用 `write_file` 保存处理结果

## 常用 jq 命令
```bash
# 格式化输出
cat data.json | jq '.'

# 提取字段
cat data.json | jq '.name, .age'

# 数组操作
cat data.json | jq '.items[0]'           # 第一个元素
cat data.json | jq '.items[]'            # 展开数组
cat data.json | jq '.items | length'     # 数组长度
cat data.json | jq '.items[] | .name'    # 提取每个元素的 name

# 过滤
cat data.json | jq '.items[] | select(.age > 18)'
cat data.json | jq '.items[] | select(.name | test("regex"))'

# 转换
cat data.json | jq '{newName: .old_name, newAge: .old_age}'

# 统计
cat data.json | jq '[.items[].age] | add / length'  # 平均值

# JSON Lines
cat data.jsonl | jq -c 'select(.type == "error")'
```

## Python JSON 处理
```python
import json

# 读取和格式化
with open('data.json') as f:
    data = json.load(f)

# 格式化输出
print(json.dumps(data, indent=2, ensure_ascii=False))

# 提取嵌套字段
value = data.get('key', {}).get('nested_key', default)

# JSON 转 CSV
import csv
with open('output.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

# 验证 JSON Schema
from jsonschema import validate
validate(instance=data, schema=schema)
```

## JSON 与其他格式互转
```bash
# JSON 转 YAML
python3 -c "import json, yaml; yaml.dump(json.load(open('data.json')), open('data.yaml', 'w'))"

# YAML 转 JSON
python3 -c "import json, yaml; json.dump(yaml.safe_load(open('data.yaml')), open('data.json', 'w'), indent=2)"

# JSON 转 CSV
python3 -c "import json, csv; data=json.load(open('data.json')); w=csv.DictWriter(open('out.csv','w'), fieldnames=data[0].keys()); w.writeheader(); w.writerows(data)"
```
