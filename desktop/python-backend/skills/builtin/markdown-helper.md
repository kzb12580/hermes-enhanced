---
name: markdown-helper
description: |
  Markdown 处理专家 — 文档编写、格式转换和模板管理。
category: productivity
tags:
  - markdown
  - document
  - format
  - writing
triggers:
  - markdown
  - md
  - 文档
  - 格式
  - 编写文档
  - README
  - 文档生成
  - 格式转换
tools:
  - read_file
  - write_file
priority: 5
---

# Markdown 处理专家

## 功能说明
帮助用户编写和处理 Markdown 文档，包括格式转换、
模板生成、目录生成、内容整理和文档结构优化。
支持标准 Markdown 和 GitHub Flavored Markdown。

## 使用场景
- 编写项目文档和 README
- 格式化已有的 Markdown 文件
- 生成文档目录（TOC）
- Markdown 转 HTML/PDF
- 批量处理 Markdown 文件
- 创建文档模板

## 工作流程
1. 使用 `read_file` 查看现有文档
2. 使用 `write_file` 创建或修改文档
3. 使用 `terminal` 执行格式转换

## Markdown 语法参考
```markdown
# 标题 1
## 标题 2
### 标题 3

**粗体** *斜体* ~~删除线~~

- 无序列表
- 项目 2

1. 有序列表
2. 项目 2

> 引用块

[链接](https://example.com)
![图片](image.png)

`行内代码`

```代码块```

| 表头1 | 表头2 |
|-------|-------|
| 单元格 | 单元格 |

---
```

## 常用转换命令
```bash
# Markdown 转 HTML
pandoc input.md -o output.html --standalone

# Markdown 转 PDF
pandoc input.md -o output.pdf --pdf-engine=xelatex

# Markdown 转 DOCX
pandoc input.md -o output.docx

# 批量转换
for f in *.md; do pandoc "$f" -o "${f%.md}.html"; done

# 生成目录
gh-md-toc README.md
```

## README 模板
```markdown
# 项目名称

简短描述。

## 功能特性
- 特性 1
- 特性 2

## 安装
```bash
pip install package
```

## 使用方法
```python
import package
```

## 贡献指南
1. Fork 项目
2. 创建分支
3. 提交 PR

## 许可证
MIT License
```

## 文档最佳实践
- 使用清晰的标题层次
- 代码块标注语言类型
- 添加适当的链接和引用
- 保持段落简洁
- 使用列表提高可读性
