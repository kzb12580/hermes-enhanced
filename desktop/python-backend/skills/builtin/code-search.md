---
name: code-search
description: |
  代码搜索专家 — 在代码库中搜索函数、类、变量和模式。
category: development
tags:
  - code
  - search
  - grep
  - ripgrep
  - function
  - class
triggers:
  - 搜索代码
  - 查找函数
  - 代码分析
  - grep
  - 代码搜索
  - 查找类
  - 查找变量
  - 代码库
  - ripgrep
  - rg
tools:
  - search_files
  - terminal
  - read_file
priority: 8
---

# 代码搜索专家

## 功能说明
在代码库中快速搜索函数定义、类声明、变量引用、导入语句
和任意正则模式。支持按文件类型过滤、上下文行显示、
以及多种输出格式。

## 使用场景
- 查找某个函数在哪些文件中被调用
- 搜索某个类的定义位置
- 按文件类型（如 .py, .ts）过滤搜索范围
- 查找 TODO、FIXME、HACK 等标记
- 分析代码库中的导入依赖关系
- 查找硬编码的字符串或常量

## 工作流程
1. 使用 `search_files` 进行内容搜索（正则匹配）
2. 使用 `read_file` 查看匹配行的上下文
3. 使用 `terminal` 执行更复杂的 grep/ripgrep 命令
4. 汇总分析结果

## 常用搜索模式
```bash
# 搜索函数定义（Python）
rg "def \w+\(" --type py

# 搜索类定义
rg "class \w+" --type py

# 搜索 import 语句
rg "^import |^from " --type py

# 搜索 TODO/FIXME
rg "TODO|FIXME|HACK|XXX" --type-add 'code:*.{py,ts,js,go,rs}'

# 搜索特定字符串并显示上下文
rg -C 3 "pattern" --type py

# 列出包含某个函数调用的文件
rg -l "function_name" .

# 搜索多行模式
rg -U "def \w+\(.*?\):" --type py

# 按文件大小限制搜索
rg --max-filesize 1M "pattern"
```

## 高级技巧
- 使用 `--type-add` 自定义文件类型
- 使用 `-g` glob 模式包含/排除目录
- 使用 `-w` 全词匹配减少误报
- 使用 `--stats` 查看搜索统计信息
