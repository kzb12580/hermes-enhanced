---
name: shell-master
description: |
  Shell 命令专家 — Bash 脚本编写和命令行操作。
category: system
tags:
  - shell
  - bash
  - command
  - script
  - terminal
triggers:
  - shell
  - bash
  - 命令
  - 脚本
  - 终端
  - 命令行
  - zsh
  - pipeline
  - 管道
tools:
  - terminal
priority: 6
---

# Shell 命令专家

## 功能说明
提供全面的 Shell 命令和 Bash 脚本编写指导，包括
常用命令组合、管道操作、脚本编写、环境变量管理和
Shell 配置等。

## 使用场景
- 编写自动化脚本
- 组合命令完成复杂任务
- 管理环境变量和 Shell 配置
- 文件批量处理
- 系统管理自动化

## 工作流程
1. 分析用户需求
2. 使用 `terminal` 提供命令或脚本
3. 解释命令的工作原理

## 常用命令组合
```bash
# --- 文件操作 ---
find . -name "*.py" -exec grep -l "import" {} \;  # 查找含 import 的 py 文件
find . -mtime -7 -type f | xargs ls -la            # 最近 7 天修改的文件
tar -czf archive.tar.gz /path/to/dir               # 创建压缩包

# --- 文本处理 ---
cat file.txt | sort | uniq -c | sort -rn           # 统计行频率
awk '{print $1}' file.txt | sort -u                 # 提取第一列去重
sed -n '10,20p' file.txt                            # 打印第 10-20 行

# --- 系统监控 ---
watch -n 5 'free -h'                                # 每 5 秒刷新内存
tail -f /var/log/syslog | grep --line-buffered ERROR # 实时过滤错误

# --- 网络 ---
curl -s http://api.example.com | jq '.'             # 格式化 JSON
nc -zv localhost 8080                                # 测试端口连通性
```

## Bash 脚本模板
```bash
#!/usr/bin/env bash
set -euo pipefail

# 日志函数
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 错误处理
trap 'log "Error on line $LINENO"; exit 1' ERR

# 主逻辑
main() {
    log "Starting..."
    # 你的代码
    log "Done."
}

main "$@"
```

## 实用技巧
```bash
# 历史命令搜索 (Ctrl+R)
# 别名设置
alias ll='ls -alF'
alias gs='git status'

# 后台运行
nohup command > output.log 2>&1 &

# 条件执行
command && echo "success" || echo "failed"

# 子shell
(cd /tmp && ls)
```
