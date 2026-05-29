"""
Hermes Desktop 工作流引擎 — 预置办公场景，一键完成
每个工作流是一个结构化 prompt + 工具调用链
"""
import json
import logging
from typing import Optional
from datetime import datetime, timedelta

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 工作流定义
# ═══════════════════════════════════════════════════════════════════════════

WORKFLOWS = {
    # ── 竞品分析报告 ──
    "competitive_analysis": {
        "name": "竞品分析报告",
        "description": "搜索竞品信息，生成对比分析 PPT",
        "icon": "📊",
        "category": "市场",
        "inputs": [
            {"name": "product", "label": "我们的产品", "type": "text", "required": True},
            {"name": "competitors", "label": "竞品（逗号分隔）", "type": "text", "required": True},
            {"name": "dimensions", "label": "分析维度", "type": "text", "default": "功能,价格,用户体验,市场份额"},
            {"name": "output", "label": "输出格式", "type": "select", "options": ["ppt", "word", "excel"], "default": "ppt"},
        ],
        "prompt_template": """你是一个市场分析师。请完成以下竞品分析任务：

## 任务
对 {product} 进行竞品分析，竞品包括：{competitors}

## 分析维度
{dimensions}

## 要求
1. 使用 web_search 搜索每个竞品的最新信息
2. 从以下维度对比：{dimensions}
3. 总结 {product} 的竞争优势和劣势
4. 给出改进建议

## 输出
{output_instruction}
""",
        "output_instructions": {
            "ppt": """使用 create_ppt 创建 PPT，theme 用 "business"：
- 第1页: 封面（标题: "{product} 竞品分析报告"）
- 第2页: 分析概述（目的、范围、方法）
- 第3页: 竞品概览（表格: 竞品名称、简介、成立时间、融资情况）
- 第4~N页: 每个维度一页对比（用 chart 或 table）
- 最后一页: 总结与建议
保存到 ~/Desktop/{product}_竞品分析.pptx""",
            "word": """使用 create_word 创建 Word 文档：
- 标题: "{product} 竞品分析报告"
- 包含: 摘要、竞品概览、各维度对比表格、SWOT分析、建议
保存到 ~/Desktop/{product}_竞品分析.docx""",
            "excel": """使用 create_excel 创建 Excel：
- Sheet1: 竞品概览（名称、简介、规模）
- Sheet2: 功能对比矩阵（功能×竞品）
- Sheet3: 价格对比
- Sheet4: 评分汇总（用 edit_excel 加图表）
保存到 ~/Desktop/{product}_竞品分析.xlsx""",
        },
    },

    # ── 周报生成 ──
    "weekly_report": {
        "name": "周报生成",
        "description": "根据本周工作内容生成格式化周报",
        "icon": "📝",
        "category": "日常",
        "inputs": [
            {"name": "work_items", "label": "本周工作内容（每行一项）", "type": "textarea", "required": True},
            {"name": "issues", "label": "遇到的问题", "type": "textarea", "default": "无"},
            {"name": "next_week", "label": "下周计划", "type": "textarea", "default": ""},
            {"name": "output", "label": "输出格式", "type": "select", "options": ["word", "email"], "default": "word"},
        ],
        "prompt_template": """你是一个专业的职场助手。请根据以下内容生成一份规范的周报：

## 本周工作
{work_items}

## 遇到的问题
{issues}

## 下周计划
{next_week}

## 要求
1. 语言正式、简洁
2. 每项工作标注完成状态（✅已完成 / 🔄进行中 / ⏳待开始）
3. 问题部分要分析原因和解决方案
4. 下周计划要有明确的时间节点
5. 最后加一段"本周总结"概述整体工作情况

## 输出
{output_instruction}
""",
        "output_instructions": {
            "word": """使用 create_word 创建：
- 标题: "周报 ({date_range})"
- 内容: 按"本周工作总结"、"问题与解决方案"、"下周工作计划"、"本周总结"分节
- font_size: 11, line_spacing: 1.5
保存到 ~/Desktop/周报_{date}.docx""",
            "email": """生成邮件正文，然后用 send_email 发送：
- 主题: "周报 ({date_range})"
- 正文: 按上述格式组织
- 如果有邮件配置就发送，否则输出正文让用户复制""",
        },
    },

    # ── 会议纪要 ──
    "meeting_minutes": {
        "name": "会议纪要",
        "description": "将会议记录/录音文字整理为规范的会议纪要",
        "icon": "📋",
        "category": "日常",
        "inputs": [
            {"name": "transcript", "label": "会议记录/录音文字", "type": "textarea", "required": True},
            {"name": "meeting_name", "label": "会议名称", "type": "text", "default": "例会"},
            {"name": "attendees", "label": "参会人员", "type": "text", "default": ""},
            {"name": "output", "label": "输出格式", "type": "select", "options": ["word", "email"], "default": "word"},
        ],
        "prompt_template": """你是一个专业的会议秘书。请将以下会议记录整理为规范的会议纪要：

## 原始记录
{transcript}

## 会议信息
- 会议名称: {meeting_name}
- 参会人员: {attendees}
- 日期: {date}

## 要求
1. 提取关键议题和讨论要点
2. 整理每项决议（明确负责人和截止时间）
3. 列出待办事项（Action Items）
4. 保持客观，不添加个人观点
5. 用结构化格式输出

## 输出
{output_instruction}
""",
        "output_instructions": {
            "word": """使用 create_word 创建：
- 标题: "{meeting_name} 会议纪要"
- 内容: 会议信息、议题摘要、决议事项、待办清单
- 表格列出 Action Items（事项、负责人、截止日期、状态）
保存到 ~/Desktop/{meeting_name}_会议纪要_{date}.docx""",
            "email": """生成邮件正文并发送：
- 主题: "{meeting_name} 会议纪要 ({date})"
- 正文: 包含完整会议纪要
- 抄送所有参会人员""",
        },
    },

    # ── 数据分析报告 ──
    "data_report": {
        "name": "数据分析报告",
        "description": "读取 Excel 数据，生成分析报告 PPT",
        "icon": "📈",
        "category": "数据",
        "inputs": [
            {"name": "file_path", "label": "Excel 文件路径", "type": "file", "required": True, "accept": ".xlsx,.xls,.csv"},
            {"name": "analysis_goal", "label": "分析目标", "type": "textarea", "required": True},
            {"name": "output", "label": "输出格式", "type": "select", "options": ["ppt", "excel", "word"], "default": "ppt"},
        ],
        "prompt_template": """你是一个数据分析师。请完成以下数据分析任务：

## 数据文件
{file_path}

## 分析目标
{analysis_goal}

## 要求
1. 先用 read_excel 读取数据，了解数据结构
2. 进行数据分析（趋势、对比、占比等）
3. 提炼关键发现和洞察
4. 生成可视化图表

## 输出
{output_instruction}
""",
        "output_instructions": {
            "ppt": """使用 create_ppt 创建数据报告 PPT，theme 用 "business"：
- 封面: 数据分析报告
- 数据概览: 数据量、维度、时间范围
- 关键发现 (3-5页): 每页一个发现，配图表
- 趋势分析: 用 chart 展示趋势
- 总结与建议
图表用 create_ppt 的 chart layout，数据用 edit_excel 写入后引用
保存到 ~/Desktop/数据分析报告_{date}.pptx""",
            "excel": """用 edit_excel 在原文件上新增"分析结果" sheet：
- 关键指标汇总
- 用 add_chart 添加图表
- 用 format_cells 格式化
保存到 ~/Desktop/数据分析_{date}.xlsx""",
            "word": """使用 create_word 创建分析报告：
- 标题、摘要、数据描述、分析结果、图表、结论
保存到 ~/Desktop/数据分析报告_{date}.docx""",
        },
    },

    # ── 邮件回复助手 ──
    "email_reply": {
        "name": "邮件回复助手",
        "description": "读取邮件并生成得体的回复",
        "icon": "✉️",
        "category": "日常",
        "inputs": [
            {"name": "email_id", "label": "邮件ID（或留空读取最新未读）", "type": "text", "default": ""},
            {"name": "tone", "label": "回复语气", "type": "select", "options": ["正式", "友好", "简洁", "详细"], "default": "正式"},
            {"name": "key_points", "label": "回复要点", "type": "textarea", "default": ""},
        ],
        "prompt_template": """你是一个专业的邮件助手。请帮我回复邮件：

## 邮件
{email_context}

## 要求
- 语气: {tone}
- 回复要点: {key_points}
- 如果没有要点，根据邮件内容自动生成得体的回复
- 回复要专业、有礼貌、言简意赅

## 操作
1. 生成回复正文
2. 用 send_email 发送回复（回复给原发件人，主题加 "Re:" 前缀）
3. 如果没有邮件配置，输出回复内容让用户复制""",
    },

    # ── 搜索调研 ──
    "research": {
        "name": "搜索调研",
        "description": "搜索特定主题并整理成结构化报告",
        "icon": "🔍",
        "category": "市场",
        "inputs": [
            {"name": "topic", "label": "调研主题", "type": "text", "required": True},
            {"name": "aspects", "label": "关注方面", "type": "text", "default": "现状、趋势、主要玩家、机会"},
            {"name": "output", "label": "输出格式", "type": "select", "options": ["word", "ppt", "excel"], "default": "word"},
        ],
        "prompt_template": """你是一个研究分析师。请对以下主题进行深度调研：

## 主题
{topic}

## 关注方面
{aspects}

## 要求
1. 使用 web_search 搜索多个角度的信息
2. 对重要网页使用 web_extract 提取详细内容
3. 交叉验证信息的准确性
4. 整理成结构化报告

## 输出
{output_instruction}
""",
        "output_instructions": {
            "word": """使用 create_word 创建调研报告：
- 标题: "{topic} 调研报告"
- 内容: 背景、现状分析、趋势、主要玩家、机会与风险、建议
- 引用来源
保存到 ~/Desktop/{topic}_调研报告_{date}.docx""",
            "ppt": """使用 create_ppt 创建调研 PPT：
- 封面、目录、各维度分析页、总结页
- theme: "modern"
保存到 ~/Desktop/{topic}_调研报告_{date}.pptx""",
            "excel": """使用 create_excel 整理数据：
- 主要信息源列表
- 对比矩阵
保存到 ~/Desktop/{topic}_调研数据_{date}.xlsx""",
        },
    },

    # ── PPT 快速生成 ──
    "quick_ppt": {
        "name": "快速 PPT",
        "description": "描述主题，自动生成 PPT",
        "icon": "🎯",
        "category": "文档",
        "inputs": [
            {"name": "topic", "label": "PPT 主题", "type": "text", "required": True},
            {"name": "pages", "label": "页数", "type": "number", "default": 10},
            {"name": "style", "label": "风格", "type": "select", "options": ["business", "tech", "modern", "minimal"], "default": "business"},
            {"name": "audience", "label": "面向对象", "type": "text", "default": "领导/团队"},
        ],
        "prompt_template": """你是一个专业的 PPT 设计师。请创建一份关于"{topic}"的 PPT：

## 要求
- 页数: {pages} 页左右
- 风格: {style}
- 面向: {audience}
- 结构清晰、内容精炼、每页要点不超过 5 条
- 先用 web_search 搜索最新数据支撑内容

## 输出
使用 create_ppt 创建 PPT：
- theme: "{style}"
- 使用多种 layout: title, bullet, two_column, chart, table, section, end
- 每页标题简洁有力
- 要点用 bullet layout
- 数据对比用 chart 或 table
保存到 ~/Desktop/{topic}.pptx""",
    },

    # ── Excel 数据整理 ──
    "excel_cleanup": {
        "name": "Excel 整理",
        "description": "整理 Excel 数据：去重、排序、格式化、加图表",
        "icon": "📋",
        "category": "数据",
        "inputs": [
            {"name": "file_path", "label": "Excel 文件路径", "type": "file", "required": True, "accept": ".xlsx,.xls"},
            {"name": "task", "label": "整理要求", "type": "textarea", "required": True},
        ],
        "prompt_template": """你是一个 Excel 专家。请按要求整理数据：

## 文件
{file_path}

## 整理要求
{task}

## 操作
1. 用 read_excel 读取数据
2. 分析数据结构和问题
3. 用 edit_excel 执行整理操作
4. 如需要，添加图表和格式化
5. 保存到原文件（或另存为新文件）""",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# 工作流执行
# ═══════════════════════════════════════════════════════════════════════════

def list_workflows() -> list[dict]:
    """列出所有可用工作流"""
    result = []
    for key, wf in WORKFLOWS.items():
        result.append({
            "id": key,
            "name": wf["name"],
            "description": wf["description"],
            "icon": wf["icon"],
            "category": wf["category"],
            "inputs": wf["inputs"],
        })
    return result


def get_workflow(workflow_id: str) -> Optional[dict]:
    """获取工作流详情"""
    return WORKFLOWS.get(workflow_id)


def build_workflow_prompt(workflow_id: str, user_inputs: dict) -> Optional[str]:
    """
    构建工作流的完整执行 prompt

    将用户输入注入到 prompt 模板中，附加输出指令
    """
    wf = WORKFLOWS.get(workflow_id)
    if not wf:
        return None

    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=6)

    # 通用变量
    variables = {
        "date": now.strftime("%Y%m%d"),
        "date_range": f"{week_start.strftime('%m.%d')}-{week_end.strftime('%m.%d')}",
        "year": str(now.year),
        "month": str(now.month),
    }

    # 用户输入
    for inp in wf["inputs"]:
        name = inp["name"]
        value = user_inputs.get(name, inp.get("default", ""))
        variables[name] = value

    # 输出指令
    output_fmt = user_inputs.get("output", "word")
    output_instructions = wf.get("output_instructions", {})
    if isinstance(output_instructions, dict):
        output_instruction = output_instructions.get(output_fmt, "生成文档保存到桌面")
    else:
        output_instruction = str(output_instructions)

    # 替换变量
    for k, v in variables.items():
        output_instruction = output_instruction.replace(f"{{{k}}}", str(v))

    variables["output_instruction"] = output_instruction

    # 构建 prompt
    prompt = wf["prompt_template"]
    for k, v in variables.items():
        prompt = prompt.replace(f"{{{k}}}", str(v))

    return prompt


# ── 工具注册 ──────────────────────────────────────────────────────────────

WORKFLOW_TOOLS = {
    "list_workflows": {"fn": list_workflows, "concurrency": "read_parallel", "description": "列出所有工作流"},
    "get_workflow": {"fn": get_workflow, "concurrency": "read_parallel", "description": "获取工作流详情"},
    "build_workflow_prompt": {"fn": build_workflow_prompt, "concurrency": "read_parallel", "description": "构建工作流prompt"},
}
