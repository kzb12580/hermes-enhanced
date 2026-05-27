---
name: docker-helper
description: |
  Docker 助手 — 容器管理、镜像操作和 Docker Compose 编排。
category: system
tags:
  - docker
  - container
  - image
  - compose
  - devops
triggers:
  - docker
  - 容器
  - 镜像
  - compose
  - dockerfile
  - 容器化
  - 部署
  - 微服务
tools:
  - terminal
priority: 6
---

# Docker 助手

## 功能说明
全面的 Docker 操作支持，包括容器生命周期管理、
镜像构建与推送、Docker Compose 编排、网络管理
和数据卷操作。

## 使用场景
- 启动、停止、重启容器
- 构建和管理 Docker 镜像
- 编排多容器应用（Docker Compose）
- 排查容器运行问题
- 管理 Docker 网络和数据卷

## 工作流程
1. 使用 `terminal` 执行 Docker 命令
2. 分析命令输出
3. 根据需要执行后续操作

## 常用 Docker 命令
```bash
# --- 容器管理 ---
docker ps                            # 运行中的容器
docker ps -a                         # 所有容器
docker start/stop/restart <name>     # 生命周期
docker rm <name>                     # 删除容器
docker exec -it <name> /bin/bash     # 进入容器
docker logs -f --tail 100 <name>     # 查看日志

# --- 镜像管理 ---
docker images                        # 列出镜像
docker build -t name:tag .           # 构建镜像
docker rmi <image>                   # 删除镜像
docker pull <image>                  # 拉取镜像
docker push <image>                  # 推送镜像
docker tag <src> <dst>               # 打标签

# --- Docker Compose ---
docker compose up -d                 # 后台启动
docker compose down                  # 停止并删除
docker compose logs -f               # 查看日志
docker compose ps                    # 查看状态
docker compose build                 # 重新构建
docker compose exec <svc> cmd        # 执行命令

# --- 网络和卷 ---
docker network ls                    # 列出网络
docker volume ls                     # 列出卷
docker system df                     # 磁盘使用
docker system prune -a               # 清理未使用资源
```

## Dockerfile 最佳实践
```dockerfile
# 使用多阶段构建
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY . .
CMD ["python", "main.py"]
```

## 排查技巧
```bash
# 容器健康检查
docker inspect --format='{{.State.Health.Status}}' <name>

# 容器资源使用
docker stats <name>

# 查看容器网络
docker inspect --format='{{json .NetworkSettings.Networks}}' <name>
```
