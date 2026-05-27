---
name: api-tester
description: |
  API 测试工具 — HTTP 请求测试、API 调试和接口验证。
category: development
tags:
  - api
  - http
  - rest
  - curl
  - testing
triggers:
  - api
  - 接口
  - 测试
  - curl
  - HTTP
  - REST
  - 请求
  - 响应
  - 状态码
  - endpoint
tools:
  - terminal
  - read_file
priority: 6
---

# API 测试工具

## 功能说明
帮助开发者测试和调试 HTTP API 接口。支持发送各种
HTTP 请求、设置请求头和参数、分析响应数据、
以及自动化 API 测试。

## 使用场景
- 测试 REST API 接口
- 调试 HTTP 请求和响应
- 验证 API 返回数据格式
- 测试认证和授权
- 性能基准测试

## 工作流程
1. 分析 API 文档或需求
2. 使用 `terminal` 发送 HTTP 请求
3. 分析响应状态码和数据
4. 根据结果调整请求参数

## 常用 curl 命令
```bash
# --- GET 请求 ---
curl http://localhost:8080/api/data
curl -v http://localhost:8080/api/data           # 详细输出

# --- POST 请求 ---
curl -X POST http://localhost:8080/api/data \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'

# --- PUT 请求 ---
curl -X PUT http://localhost:8080/api/data/1 \
  -H "Content-Type: application/json" \
  -d '{"key": "new_value"}'

# --- DELETE 请求 ---
curl -X DELETE http://localhost:8080/api/data/1

# --- 认证 ---
curl -H "Authorization: Bearer <token>" http://api.example.com
curl -u username:password http://api.example.com

# --- 文件上传 ---
curl -F "file=@/path/to/file" http://localhost:8080/upload

# --- 保存响应 ---
curl -o response.json http://api.example.com/data

# --- 跟随重定向 ---
curl -L http://example.com

# --- 设置超时 ---
curl --connect-timeout 5 --max-time 30 http://api.example.com
```

## Python requests 测试
```python
import requests

# GET
r = requests.get('http://localhost:8080/api/data')
print(r.status_code, r.json())

# POST
r = requests.post('http://localhost:8080/api/data',
                   json={'key': 'value'},
                   headers={'Authorization': 'Bearer token'})
print(r.status_code, r.json())

# 批量测试
endpoints = ['/api/users', '/api/posts', '/api/comments']
for ep in endpoints:
    r = requests.get(f'http://localhost:8080{ep}')
    print(f'{ep}: {r.status_code}')
```

## 响应状态码参考
- **2xx** 成功: 200 OK, 201 Created, 204 No Content
- **3xx** 重定向: 301 Moved, 302 Found, 304 Not Modified
- **4xx** 客户端错误: 400 Bad Request, 401 Unauthorized, 404 Not Found
- **5xx** 服务端错误: 500 Internal Error, 502 Bad Gateway, 503 Unavailable
