---
name: web-research
description: |
  网络研究专家 — 搜索互联网信息、提取网页内容和整理研究资料。
category: web
tags:
  - web
  - search
  - research
  - information
triggers:
  - 搜索
  - 查找
  - 研究
  - 信息
  - 资料
  - 网络
  - 网页
  - 搜索引擎
  - 调查
  - 百科
tools:
  - web_search
  - web_extract
  - terminal
priority: 6
---

# 网络研究专家

## 功能说明
帮助用户在互联网上搜索信息、提取网页内容、整理研究资料。
支持多关键词搜索、网页内容提取、信息对比和总结。

## 使用场景
- 搜索技术文档和教程
- 查找开源项目和库的信息
- 研究某个技术方案的优劣
- 提取特定网页的文本内容
- 对比不同来源的信息

## 工作流程
1. 使用 `web_search` 搜索关键词获取结果列表
2. 使用 `web_extract` 提取相关网页的详细内容
3. 分析和整理提取的信息
4. 总结研究发现

## 搜索技巧
```
# 精确匹配
"exact phrase search"

# 排除关键词
search term -exclude

# 指定网站
site:github.com search term

# 文件类型
filetype:pdf search term

# 时间范围
search term after:2024-01-01

# 组合搜索
"exact phrase" site:stackoverflow.com -closed
```

## 研究方法论
1. **广泛搜索** — 先用通用关键词了解概况
2. **精确搜索** — 用更具体的术语缩小范围
3. **交叉验证** — 从多个来源确认信息
4. **记录来源** — 保存 URL 和关键引用
5. **整理总结** — 将发现整理成结构化笔记

## 输出格式建议
```markdown
## 研究主题
简述研究目标

## 关键发现
1. 发现一（来源: URL）
2. 发现二（来源: URL）

## 对比分析
- 方案 A: 优点/缺点
- 方案 B: 优点/缺点

## 推荐结论
基于研究的建议
```
