---
name: cron-helper
description: |
  定时任务助手 — Cron 任务的创建、管理和调试。
category: system
tags:
  - cron
  - schedule
  - timer
  - automation
triggers:
  - 定时
  - 计划
  - cron
  - 周期
  - 定时任务
  - 计划任务
  - 调度
  - 定时执行
  - crontab
tools:
  - terminal
priority: 5
---

# 定时任务助手

## 功能说明
帮助用户创建和管理 Cron 定时任务，包括 cron
表达式编写、任务调度配置、任务调试和日志查看。

## 使用场景
- 创建定时执行的任务
- 编写 cron 表达式
- 管理已有的 cron 任务
- 调试定时任务执行问题
- 查看任务执行日志

## 工作流程
1. 分析用户的定时需求
2. 编写 cron 表达式
3. 使用 `terminal` 配置 crontab
4. 验证任务是否正常执行

## Cron 表达式语法
```
┌───────────── 分钟 (0-59)
│ ┌───────────── 小时 (0-23)
│ │ ┌───────────── 日 (1-31)
│ │ │ ┌───────────── 月 (1-12)
│ │ │ │ ┌───────────── 星期几 (0-7, 0和7都是周日)
│ │ │ │ │
* * * * * command

# 特殊字符
*        任意值
,        列表 (1,3,5)
-        范围 (1-5)
/        步长 (*/5)
```

## 常用 Cron 示例
```bash
# 每分钟执行
* * * * * /path/to/script.sh

# 每小时执行
0 * * * * /path/to/script.sh

# 每天凌晨 2 点
0 2 * * * /path/to/backup.sh

# 每周一早上 9 点
0 9 * * 1 /path/to/report.sh

# 每月 1 号
0 0 1 * * /path/to/monthly.sh

# 每 5 分钟
*/5 * * * * /path/to/check.sh

# 工作日（周一到周五）每天 8 点
0 8 * * 1-5 /path/to/workday.sh

# 每天 8 点和 20 点
0 8,20 * * * /path/to/twice-daily.sh
```

## Crontab 管理命令
```bash
crontab -l                    # 列出当前用户的 cron 任务
crontab -e                    # 编辑 cron 任务
crontab -r                    # 删除所有 cron 任务
crontab -u username -l        # 查看指定用户的任务
```

## 调试技巧
```bash
# 查看 cron 日志
grep CRON /var/log/syslog
journalctl -u cron

# 手动测试脚本
/path/to/script.sh 2>&1 | tee /tmp/test.log

# 确保脚本可执行
chmod +x /path/to/script.sh

# 在 cron 中使用完整路径
# PATH 可能与交互式 shell 不同

# 输出重定向（避免邮件通知）
* * * * * /path/to/script.sh >> /var/log/cron.log 2>&1
```

## 最佳实践
- 使用完整路径（命令和文件路径）
- 将输出重定向到日志文件
- 先手动测试脚本再加入 cron
- 使用 `flock` 防止任务重叠执行
- 记录每个 cron 任务的用途
```bash
# 使用 flock 防止重叠
* * * * * flock -n /tmp/task.lock /path/to/script.sh
```

## systemd timer 替代方案
```ini
# /etc/systemd/system/backup.timer
[Unit]
Description=Daily Backup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```
```bash
systemctl enable --now backup.timer
systemctl list-timers
```
