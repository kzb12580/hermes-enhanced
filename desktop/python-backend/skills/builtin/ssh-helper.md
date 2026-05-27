---
name: ssh-helper
description: |
  SSH 助手 — 远程服务器连接、文件传输和隧道管理。
category: system
tags:
  - ssh
  - remote
  - server
  - tunnel
  - scp
triggers:
  - ssh
  - 远程
  - 连接
  - 服务器
  - 远程服务器
  - SCP
  - SFTP
  - 隧道
  - 端口转发
  - 密钥
tools:
  - terminal
priority: 5
---

# SSH 助手

## 功能说明
提供全面的 SSH 操作支持，包括远程服务器连接、
文件传输（SCP/SFTP）、SSH 隧道和端口转发、
密钥管理和 SSH 配置优化。

## 使用场景
- 连接远程服务器
- 在本地和远程之间传输文件
- 设置 SSH 隧道访问内网服务
- 管理 SSH 密钥
- 配置 SSH 别名和跳板机

## 工作流程
1. 分析用户的远程连接需求
2. 使用 `terminal` 执行 SSH 命令
3. 提供连接和操作指导

## 常用 SSH 命令
```bash
# --- 基础连接 ---
ssh user@hostname                     # 基础连接
ssh -p 2222 user@hostname             # 指定端口
ssh -i ~/.ssh/key.pem user@hostname   # 使用密钥

# --- 文件传输 ---
scp file.txt user@host:/path/         # 上传文件
scp user@host:/path/file.txt ./       # 下载文件
scp -r dir/ user@host:/path/          # 上传目录
rsync -avz dir/ user@host:/path/      # 同步目录

# --- SSH 隧道 ---
# 本地转发（访问远程服务）
ssh -L 8080:localhost:80 user@host
# 远程转发（暴露本地服务）
ssh -R 9090:localhost:3000 user@host
# 动态代理（SOCKS5）
ssh -D 1080 user@host

# --- 跳板机 ---
ssh -J jump@bastion user@target
# 或在 ~/.ssh/config 中配置

# --- 密钥管理 ---
ssh-keygen -t ed25519 -C "email@example.com"  # 生成密钥
ssh-copy-id user@host                         # 复制公钥
ssh-add ~/.ssh/id_ed25519                     # 添加到 agent
```

## SSH 配置文件
```bash
# ~/.ssh/config
Host myserver
    HostName 192.168.1.100
    User admin
    Port 22
    IdentityFile ~/.ssh/id_ed25519

Host jumphost
    HostName bastion.example.com
    User jumpuser
    ProxyJump none

Host internal
    HostName 10.0.0.5
    User admin
    ProxyJump jumphost
```

## 安全建议
- 使用密钥认证，禁用密码登录
- 使用 Ed25519 密钥类型
- 定期轮换密钥
- 限制 SSH 访问 IP
- 使用非标准端口
- 启用双因素认证

## 排查连接问题
```bash
ssh -v user@host              # 详细输出
ssh -T git@github.com         # 测试连接
telnet host 22                # 测试端口
nc -zv host 22                # 测试连通性
```
