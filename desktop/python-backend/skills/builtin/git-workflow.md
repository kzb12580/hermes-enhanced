---
name: git-workflow
description: |
  Git 工作流专家 — 版本控制、分支管理和协作开发。
category: development
tags:
  - git
  - version-control
  - branch
  - commit
  - merge
triggers:
  - git
  - 提交
  - 分支
  - 合并
  - 版本
  - commit
  - push
  - pull
  - rebase
  - stash
  - tag
tools:
  - terminal
priority: 7
---

# Git 工作流专家

## 功能说明
提供全面的 Git 操作指导，包括日常提交、分支管理、
合并冲突解决、历史查看和仓库维护等。支持多种工作流
模式（Git Flow、GitHub Flow、Trunk-based）。

## 使用场景
- 日常代码提交和推送
- 创建和管理分支
- 解决合并冲突
- 查看和搜索提交历史
- 回滚错误的提交
- 管理远程仓库

## 工作流程
1. 使用 `terminal` 执行 Git 命令
2. 分析命令输出
3. 根据需要执行后续操作

## 常用 Git 命令
```bash
# --- 基础操作 ---
git status                          # 查看状态
git add .                           # 暂存所有更改
git commit -m "message"             # 提交
git push origin main                # 推送
git pull --rebase                   # 拉取并变基

# --- 分支管理 ---
git branch                          # 列出分支
git checkout -b feature/new-feature # 创建并切换分支
git merge feature/new-feature       # 合并分支
git branch -d feature/old-branch    # 删除分支

# --- 历史查看 ---
git log --oneline -20               # 最近 20 条提交
git log --graph --oneline --all     # 图形化分支历史
git blame file.py                   # 查看每行的修改者
git diff HEAD~3                     # 与 3 个提交前对比

# --- 暂存和恢复 ---
git stash                           # 暂存工作区
git stash pop                       # 恢复暂存
git checkout -- file.py             # 丢弃文件更改
git reset HEAD~1                    # 回退一个提交（保留更改）

# --- 标签 ---
git tag v1.0.0                      # 创建标签
git push origin v1.0.0              # 推送标签

# --- 远程仓库 ---
git remote -v                       # 查看远程
git remote add origin <url>         # 添加远程
git fetch --all                     # 获取所有远程更新
```

## 合并冲突解决
```bash
# 查看冲突文件
git status

# 编辑冲突文件，解决 <<<<<<< HEAD ... ======= ... >>>>>>> 标记

# 标记为已解决
git add <resolved-file>

# 完成合并
git commit
```

## 提交消息规范
```
<type>(<scope>): <subject>

类型: feat, fix, docs, style, refactor, test, chore
示例: feat(auth): add OAuth2 login support
```
