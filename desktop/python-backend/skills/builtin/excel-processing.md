---
name: excel-processing
description: "Excel 处理 — 读写、筛选、统计、图表、格式化"
category: office
version: "1.0"
tags: [excel, xlsx, spreadsheet, data, office]
---

# Excel 处理技能

## 工具依赖
- Python: openpyxl, pandas

## 安装
```bash
pip install openpyxl pandas
```

## 常用操作

### 1. 读取 Excel
```python
import pandas as pd

df = pd.read_excel('data.xlsx', sheet_name='Sheet1')
print(df.head())
print(df.describe())
```

### 2. 写入 Excel
```python
import pandas as pd

df = pd.DataFrame({'姓名': ['张三', '李四'], '分数': [90, 85]})
df.to_excel('output.xlsx', index=False, sheet_name='成绩')
```

### 3. 多 Sheet 读写
```python
import pandas as pd

# 读取所有 sheet
sheets = pd.read_excel('data.xlsx', sheet_name=None)
for name, df in sheets.items():
    print(f'{name}: {len(df)} rows')

# 写入多个 sheet
with pd.ExcelWriter('output.xlsx') as writer:
    df1.to_excel(writer, sheet_name='汇总', index=False)
    df2.to_excel(writer, sheet_name='明细', index=False)
```

### 4. 数据筛选
```python
import pandas as pd

df = pd.read_excel('data.xlsx')
# 筛选条件
filtered = df[df['分数'] > 80]
# 多条件
filtered = df[(df['分数'] > 80) & (df['班级'] == '一班')]
# 保存
filtered.to_excel('filtered.xlsx', index=False)
```

### 5. 数据统计
```python
import pandas as pd

df = pd.read_excel('data.xlsx')
# 基本统计
print(df['分数'].mean())  # 平均分
print(df['分数'].max())   # 最高分
print(df['分数'].min())   # 最低分
print(df.groupby('班级')['分数'].mean())  # 按班级平均分
```

### 6. 用 openpyxl 操作单元格
```python
from openpyxl import Workbook, load_workbook

# 创建并写入
wb = Workbook()
ws = wb.active
ws['A1'] = '姓名'
ws['B1'] = '分数'
ws['A2'] = '张三'
ws['B2'] = 90
wb.save('new.xlsx')

# 读取并修改
wb = load_workbook('data.xlsx')
ws = wb.active
for row in ws.iter_rows(min_row=2, values_only=True):
    print(row)
```

### 7. 格式化
```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

wb = Workbook()
ws = wb.active
ws['A1'] = '标题'
ws['A1'].font = Font(bold=True, size=14)
ws['A1'].fill = PatternFill('solid', fgColor='CCCCCC')
ws['A1'].alignment = Alignment(horizontal='center')
wb.save('formatted.xlsx')
```

### 8. 合并多个 Excel
```python
import pandas as pd
import glob

files = glob.glob('data/*.xlsx')
dfs = [pd.read_excel(f) for f in files]
combined = pd.concat(dfs, ignore_index=True)
combined.to_excel('combined.xlsx', index=False)
```

## 注意事项
- pandas 适合数据分析，openpyxl 适合精细操作
- 大文件用 `read_excel(..., chunksize=10000)` 分块读取
- 保存时 `index=False` 避免多出序号列
