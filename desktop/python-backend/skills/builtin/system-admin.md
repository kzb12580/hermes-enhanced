---
name: system-admin
description: |
  系统管理专家 — 进程管理、服务控制、系统监控和资源分析。
category: system
tags:
  - system
  - process
  - service
  - monitor
  - admin
triggers:
  - 进程
  - 服务
  - 系统
  - 监控
  - 管理
  - 内存
  - CPU
  - 磁盘
  - 网络
  - 端口
  - 权限
tools:
  - terminal
priority: 7
---

# 系统管理专家

## 功能说明
提供全面的系统管理能力，包括进程查看与控制、服务管理、
系统资源监控（CPU、内存、磁盘、网络）、用户管理和
权限设置等常用运维操作。

## 使用场景
- 查看和管理运行中的进程
- 启动/停止/重启系统服务
- 监控系统资源使用情况
- 查看网络连接和端口占用
- 管理用户和权限
- 查看系统日志

## 工作流程
1. 使用 `terminal` 执行系统命令
2. 分析输出结果
3. 根据需要执行管理操作
4. 验证操作结果

## 常用命令参考
```bash
# --- 进程管理 ---
ps aux --sort=-%mem | head -20       # 按内存排序前 20 进程
ps aux --sort=-%cpu | head -20       # 按 CPU 排序
top -bn1 | head -20                  # 快照式 top 输出
kill -9 <PID>                        # 强制终止进程
pkill -f "pattern"                   # 按名称终止进程

# --- 系统资源 ---
free -h                              # 内存使用
df -h                                # 磁盘使用
du -sh /path/*                       # 目录大小
uptime                               # 系统负载
vmstat 1 5                           # 虚拟内存统计

# --- 网络 ---
ss -tlnp                             # 监听端口
netstat -tlnp                        # 监听端口（旧版）
curl -I http://localhost:8080        # HTTP 健康检查
ip addr show                         # 网络接口

# --- 服务管理 ---
systemctl status <service>           # 服务状态
systemctl restart <service>          # 重启服务
journalctl -u <service> -f           # 实时日志

# --- 用户管理 ---
whoami                               # 当前用户
id <user>                            # 用户信息
chmod 755 file                       # 修改权限
chown user:group file                # 修改所有者
```

## 注意事项
- 杀进程前先确认进程用途
- 修改系统配置前建议备份
- 操作系统服务需要适当的权限
