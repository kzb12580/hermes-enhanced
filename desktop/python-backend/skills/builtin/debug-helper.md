---
name: debug-helper
description: |
  调试助手 — 错误排查、日志分析和问题诊断。
category: development
tags:
  - debug
  - error
  - log
  - troubleshoot
  - bug
triggers:
  - 调试
  - 错误
  - 日志
  - 排查
  - bug
  - 异常
  - 报错
  - 崩溃
  - 问题
  - 诊断
tools:
  - search_files
  - terminal
  - read_file
priority: 8
---

# 调试助手

## 功能说明
帮助开发者快速定位和解决代码中的错误和问题。
提供系统化的排查方法、日志分析技巧和常见错误的
解决方案。

## 使用场景
- 分析程序崩溃的错误信息
- 排查性能瓶颈
- 分析日志文件中的异常
- 调试网络连接问题
- 解决依赖冲突
- 内存泄漏排查

## 工作流程
1. 收集错误信息（日志、堆栈跟踪、错误消息）
2. 使用 `search_files` 在代码中定位相关代码
3. 使用 `read_file` 查看相关源文件
4. 使用 `terminal` 运行诊断命令
5. 分析根因并提供修复方案

## 常用调试命令
```bash
# --- Python 调试 ---
python3 -m pdb script.py           # 启动调试器
python3 -c "import traceback; ..."  # 堆栈跟踪
pip list | grep <package>           # 检查依赖

# --- 进程调试 ---
strace -p <PID>                     # 系统调用追踪
lsof -p <PID>                       # 打开的文件
cat /proc/<PID>/status              # 进程状态

# --- 网络调试 ---
curl -v http://localhost:8080       # 详细 HTTP 请求
tcpdump -i lo port 8080             # 抓包
nslookup hostname                   # DNS 解析

# --- 日志分析 ---
journalctl -u <service> --since "1h ago"
tail -f /var/log/syslog
grep -i error /var/log/app.log
```

## 常见错误模式
| 错误类型 | 排查方向 |
|---------|---------|
| ImportError | 检查包是否安装、路径是否正确 |
| FileNotFoundError | 检查文件路径、权限 |
| ConnectionError | 检查服务是否运行、端口是否正确 |
| MemoryError | 检查数据大小、是否有内存泄漏 |
| Timeout | 检查网络、服务响应时间 |

## 调试最佳实践
1. **复现问题** — 确保能稳定重现
2. **最小化** — 缩小问题范围
3. **查看日志** — 从日志中找线索
4. **二分法** — 逐步排除可能原因
5. **搜索错误信息** — 将错误信息作为关键词搜索
