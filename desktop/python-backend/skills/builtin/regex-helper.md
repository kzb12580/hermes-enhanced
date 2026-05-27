---
name: regex-helper
description: |
  正则表达式助手 — 正则表达式编写、测试和优化。
category: development
tags:
  - regex
  - regular-expression
  - pattern
  - match
triggers:
  - 正则
  - regex
  - 匹配
  - 模式
  - regular expression
  - re
  - regexp
  - 正则表达式
tools:
  - terminal
  - search_files
priority: 6
---

# 正则表达式助手

## 功能说明
帮助用户编写、测试和优化正则表达式。提供常用正则
模式参考、调试技巧和性能优化建议。支持 Python、
JavaScript、Go 等多种语言的正则语法。

## 使用场景
- 编写匹配特定模式的正则表达式
- 测试和调试已有的正则表达式
- 从文本中提取结构化数据
- 验证输入格式（邮箱、手机号、URL 等）
- 批量文本替换

## 工作流程
1. 分析用户的匹配需求
2. 编写正则表达式
3. 使用 `terminal` 测试正则表达式
4. 使用 `search_files` 在文件中验证匹配结果

## 常用正则模式
```
# 基础元字符
.        任意字符（除换行）
\d       数字 [0-9]
\w       单词字符 [a-zA-Z0-9_]
\s       空白字符
\b       单词边界

# 量词
*        0 次或多次
+        1 次或多次
?        0 次或 1 次
{n}      恰好 n 次
{n,m}    n 到 m 次

# 分组和引用
(abc)    捕获组
(?:abc)  非捕获组
\1       反向引用

# 零宽断言
(?=...)  正向前瞻
(?!...)  负向前瞻
(?<=...) 正向后顾
(?<!...) 负向后顾
```

## 常用正则表达式
```python
import re

# 邮箱
r'[\w.-]+@[\w.-]+\.\w+'

# 手机号（中国大陆）
r'1[3-9]\d{9}'

# URL
r'https?://[\w./-]+'

# IPv4 地址
r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'

# 日期 (YYYY-MM-DD)
r'\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])'

# HTML 标签
r'<(\w+)[^>]*>.*?</\1>'
```

## 测试命令
```bash
# Python 测试
python3 -c "import re; print(re.findall(r'\d+', 'abc123def456'))"

# grep 正则
grep -E "pattern" file.txt
grep -P "pattern" file.txt  # Perl 正则

# ripgrep
rg "pattern" file.txt
```

## 性能优化
- 避免嵌套量词 `(a+)+`
- 使用非捕获组 `(?:...)` 当不需要引用时
- 使用原子组或占有量词避免回溯
- 锚定匹配位置 `^pattern$`
