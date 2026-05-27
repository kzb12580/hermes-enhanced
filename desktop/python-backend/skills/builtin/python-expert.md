---
name: python-expert
description: |
  Python 专家 — Python 开发、包管理、虚拟环境和最佳实践。
category: development
tags:
  - python
  - pip
  - venv
  - package
  - pypi
triggers:
  - python
  - pip
  - 虚拟环境
  - 包管理
  - pypi
  - conda
  - poetry
  - requirements
  - venv
  - pipenv
tools:
  - terminal
  - read_file
priority: 7
---

# Python 专家

## 功能说明
全面的 Python 开发支持，包括环境管理、包安装与管理、
代码质量工具、测试框架和性能优化等。支持 pip、poetry、
conda 等多种包管理工具。

## 使用场景
- 创建和管理 Python 虚拟环境
- 安装和管理 Python 包
- 运行和调试 Python 脚本
- 代码格式化和 linting
- 运行测试套件
- 性能分析和优化

## 工作流程
1. 使用 `read_file` 查看项目配置文件
2. 使用 `terminal` 执行 Python 相关命令
3. 分析输出并提供优化建议

## 常用命令
```bash
# --- 虚拟环境 ---
python3 -m venv .venv                # 创建虚拟环境
source .venv/bin/activate            # 激活（Linux/Mac）
.venv\Scripts\activate               # 激活（Windows）
deactivate                           # 退出虚拟环境

# --- 包管理 (pip) ---
pip install package                  # 安装包
pip install -r requirements.txt      # 从文件安装
pip install package==1.2.3           # 指定版本
pip install --upgrade package        # 升级
pip uninstall package                # 卸载
pip list                             # 列出已安装
pip freeze > requirements.txt        # 导出依赖

# --- 包管理 (poetry) ---
poetry install                       # 安装依赖
poetry add package                   # 添加包
poetry run python script.py          # 运行脚本
poetry build                         # 构建包
poetry publish                       # 发布到 PyPI

# --- 代码质量 ---
python3 -m ruff check .              # Linting
python3 -m ruff format .             # 格式化
python3 -m mypy .                    # 类型检查
python3 -m black .                   # 格式化（Black）

# --- 测试 ---
python3 -m pytest                    # 运行测试
python3 -m pytest -v                 # 详细输出
python3 -m pytest --cov              # 覆盖率
python3 -m pytest -x                 # 首次失败即停止

# --- 性能分析 ---
python3 -m cProfile script.py        # 性能分析
python3 -m memory_profiler script.py # 内存分析
```

## 项目结构最佳实践
```
project/
├── src/
│   └── package/
│       ├── __init__.py
│       └── module.py
├── tests/
│   └── test_module.py
├── pyproject.toml
├── requirements.txt
└── README.md
```
