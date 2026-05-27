---
name: log-analyzer
description: |
  日志分析专家 — 系统和应用日志的分析与排查。
category: system
tags:
  - log
  - analysis
  - troubleshoot
  - monitoring
triggers:
  - 日志
  - 分析
  - log
  - 排查
  - 日志分析
  - 错误日志
  - 访问日志
  - 系统日志
  - syslog
tools:
  - read_file
  - search_files
  - terminal
priority: 7
---

# 日志分析专家

## 功能说明
帮助用户分析系统日志、应用日志和访问日志，
快速定位错误、异常和性能问题。支持多种日志格式
的解析和统计。

## 使用场景
- 分析应用程序错误日志
- 排查系统故障
- 统计访问日志中的请求模式
- 识别异常访问和安全事件
- 性能瓶颈分析

## 工作流程
1. 使用 `read_file` 或 `search_files` 定位相关日志
2. 使用 `terminal` 执行日志分析命令
3. 提取关键信息（错误、警告、异常）
4. 生成分析报告

## 常用日志分析命令
```bash
# --- 实时监控 ---
tail -f /var/log/app.log
tail -f /var/log/app.log | grep --line-buffered -i error

# --- 错误提取 ---
grep -i "error\|exception\|fatal" /var/log/app.log
grep -c "ERROR" /var/log/app.log                   # 错误计数

# --- 时间范围过滤 ---
awk '/2024-01-15 10:00/,/2024-01-15 11:00/' app.log

# --- 统计分析 ---
# 按小时统计请求数
awk '{print $4}' access.log | cut -d: -f2 | sort | uniq -c

# HTTP 状态码统计
awk '{print $9}' access.log | sort | uniq -c | sort -rn

# 最频繁的 IP
awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -20

# 响应时间最大的请求
sort -t' ' -k10 -rn access.log | head -20

# --- 日志格式化 ---
# Nginx 访问日志分析
awk '{print $1, $7, $9, $11}' access.log

# 提取特定字段
sed -E 's/.*\[(.*)\].*/\1/' app.log               # 提取时间戳
```

## 日志级别说明
- **FATAL/CRITICAL** — 致命错误，系统无法继续运行
- **ERROR** — 错误，某个操作失败
- **WARN/WARNING** — 警告，潜在问题
- **INFO** — 信息，正常操作记录
- **DEBUG** — 调试，详细开发信息

## 分析报告模板
```markdown
## 日志分析报告
- **时间范围**: 2024-01-15 10:00 - 11:00
- **日志文件**: /var/log/app.log
- **总行数**: 15,432

## 错误统计
- ERROR: 23 次
- WARN: 156 次

## 关键发现
1. 10:15 出现集中错误，原因是数据库连接超时
2. API /users 端点平均响应时间 2.3s

## 建议
1. 增加数据库连接池大小
2. 优化 /users 端点查询
```
