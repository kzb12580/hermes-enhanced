"""
Model-specific system prompt profiles.

Hardcoded profiles for mainstream models provide "super-optimized" guidance
tailored to each model's known strengths and weaknesses.

Custom models can be added via hot-updatable .md files in the
`model_profiles/` directory — see `get_model_profile()` for merge logic.

Architecture:
  1. Model name comes from config["model"] or ChatMessage.model
  2. `detect_model_family()` normalizes the name → family key
  3. HARDCODED_PROFILES[family] returns the hardcoded optimization
  4. Hot-update .md files in model_profiles/ can OVERRIDE or EXTEND
  5. Final profile is appended to the system prompt
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes-backend.model_profiles")

# ─── Hot-update directory (relative to this file) ──────────────────────────
_PROFILES_DIR = Path(__file__).parent / "model_profiles"


# ═══════════════════════════════════════════════════════════════════════════
# MODEL FAMILY DETECTION
# ═══════════════════════════════════════════════════════════════════════════

# Patterns checked in order — first match wins
_FAMILY_PATTERNS: list[tuple[str, list[str]]] = [
    # Xiaomi MIMO
    ("mimo", ["mimo", "xiaomi"]),
    # DeepSeek
    ("deepseek", ["deepseek", "deep-seek"]),
    # Anthropic Claude
    ("claude", ["claude", "anthropic"]),
    # OpenAI GPT (including open-source GPT-OSS)
    ("gpt", ["gpt-4", "gpt4", "gpt-3", "gpt3", "gpt-oss", "o1-", "o1-preview", "o1-mini", "o3-", "o3-mini", "o4"]),
    # Google Gemini / Gemma
    ("gemini", ["gemini", "gemma", "bard"]),
    # Alibaba Qwen
    ("qwen", ["qwen", "tongyi"]),
    # Meta Llama + NVIDIA Nemotron (Llama-based)
    ("llama", ["llama", "meta-llama", "nemotron", "nvidia"]),
    # Mistral / Mixtral
    ("mistral", ["mistral", "mixtral", "ministral"]),
    # Yi (01.AI)
    ("yi", ["yi-", "01-ai"]),
    # GLM (Zhipu)
    ("glm", ["glm", "chatglm", "zhipu"]),
    # Moonshot / Kimi
    ("moonshot", ["moonshot", "kimi"]),
    # InternLM
    ("internlm", ["internlm", "intern"]),
    # Grok (xAI)
    ("grok", ["grok", "x-ai"]),
    # MiniMax
    ("minimax", ["minimax"]),
    # Step (StepFun)
    ("step", ["step-", "stepfun"]),
    # Microsoft Phi
    ("phi", ["phi-"]),
    # Upstage Solar
    ("solar", ["solar"]),
]


def detect_model_family(model_name: Optional[str]) -> str:
    """Detect model family from a model name string.
    
    Returns a normalized family key (e.g. "mimo", "deepseek", "claude")
    or "default" if no match.
    """
    if not model_name:
        return "default"
    name_lower = model_name.lower().strip()
    for family, patterns in _FAMILY_PATTERNS:
        for pattern in patterns:
            if pattern in name_lower:
                return family
    return "default"


# ═══════════════════════════════════════════════════════════════════════════
# HARDCODED PROFILES — Mainstream models get "super-optimized" prompts
# ═══════════════════════════════════════════════════════════════════════════

HARDCODED_PROFILES: dict[str, str] = {

# ─── MIMO (Xiaomi) ──────────────────────────────────────────────────────
"mimo": """## 🎯 MIMO 模型专属优化策略

你运行在 **MIMO (小米)** 模型上。以下是针对 MIMO 的关键优化规则，**必须严格遵守**：

### ⚡ 参数控制（最高优先级）
- **工具参数必须极简** — 每个参数只传必要值，绝不传默认值或空值
- **禁止深层嵌套** — slides 数组最多 2 层，对象属性最多 3 层
- **单次参数不超过 3KB** — 超过就用 write_file 写文件再传文件路径
- **slides_file 优先** — 超过 5 页的 PPT 必须用 `write_file("slides.json", ...)` + `create_ppt(path, slides_file="slides.json")`
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- **不要在 tool_call 的 arguments 里写大段 JSON** — 写文件传路径

### 🚫 MIMO 常见陷阱
1. **JSON 截断** — MIMO 生成长 JSON 容易被截断（Unterminated string），所以参数越短越好
2. **重复尝试** — 失败 2 次后必须换方案，不要一直重试同一个方法
3. **不要写 Python 脚本生成 PPT** — 用 create_ppt 工具，不要用 python-pptx
4. **不要自己实现动画** — 用 animate_ppt 工具，不要自己拼 XML 或写 COM 脚本
5. **动画工作流**: create_ppt(创建) → list_ppt_shapes(查看形状) → animate_ppt(加动画)
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML

### ✅ MIMO 最佳实践
- 先 `write_file` 写数据文件，再调用工具读取 — 比内联参数稳定 10 倍
- 复杂任务用 `todo_create` 分步 — 防止 MIMO 一次性处理太多
- 每步完成后 `verify_file` — MIMO 有时会"假装"完成
- 中文回复，简洁直接

### 📐 工具调用格式
```json
{"name": "tool_name", "arguments": {"key": "value"}}
```
- arguments 必须是合法 JSON，字符串用双引号
- 不要在 arguments 里写注释
- 不要省略必需参数
""",

# ─── DeepSeek ───────────────────────────────────────────────────────────
"deepseek": """## 🎯 DeepSeek 模型专属优化策略

你运行在 **DeepSeek** 模型上。以下是针对 DeepSeek 的关键优化规则：

### ⚡ DeepSeek 核心优势
- 结构化输出能力强 — 善用 JSON 格式
- 长文本稳定性好 — 可以内联较大参数
- 中文理解优秀 — 直接用中文交互

### 📐 工具调用规范
- DeepSeek 工具调用格式稳定，直接使用即可
- 参数可以稍微丰富，但单次不超过 8KB
- slides_file 用于 >10 页的 PPT

### ⚠️ DeepSeek 注意事项
- 有时会在工具调用前输出过多分析文字 — 直接调用，少分析
- 遇到错误时，先看错误信息再换方案 — 不要盲目重试
- 复杂任务用 todo_create 分步跟踪

### 🎨 文档创建优化
- PPT: 用 create_ppt 工具（PptxGenJS），不要用 python-pptx
- **PPT 动画**: 用 animate_ppt 工具，不要自己写 Python 脚本拼 XML
- Word: 用 create_word 工具，支持模板和格式化
- Excel: 用 create_excel / edit_excel 工具
- 不要用 execute_code 自己写 Office 文件 — 用专用工具
""",

# ─── Claude ─────────────────────────────────────────────────────────────
"claude": """## 🎯 Claude 模型专属优化策略

你运行在 **Claude (Anthropic)** 模型上。以下是关键优化规则：

### ⚡ Claude 核心优势
- 推理能力强 — 适合复杂多步任务
- 代码生成质量高 — 但要用工具，不要只输出代码
- 长上下文稳定 — 可以处理大量数据

### 📐 工具调用规范
- Claude 工具调用格式严格，确保 JSON 完全合法
- 不要在 tool_call 前输出大段分析 — 直接调用
- 参数中不要包含 markdown 格式 — 纯 JSON

### ⚠️ Claude 注意事项
- Claude 有时会"过度解释" — 简洁回复，少说多做
- 不要假设用户需要确认 — 直接执行合理默认值
- 复杂任务用 todo_create 分步，每步完成后标记 completed

### 🎨 文档创建
- PPT: 用 create_ppt 工具（PptxGenJS），不要用 python-pptx
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- PPT 过渡动画: slide 定义中加 `"transition": {"type": "fade", "duration": 1}`
- Word/Excel: 用专用工具，不要自己写脚本
""",

# ─── GPT-4o / OpenAI ───────────────────────────────────────────────────
"gpt": """## 🎯 GPT 模型专属优化策略

你运行在 **GPT (OpenAI)** 模型上。以下是关键优化规则：

### ⚡ GPT 核心优势
- 全面均衡 — 各方面表现稳定
- 函数调用成熟 — 工具使用准确
- 多语言支持好 — 但中文长文本偶有退化

### 📐 工具调用规范
- 使用标准 function calling，参数准确
- 复杂参数可以内联（GPT 处理能力较强）
- slides_file 用于 >10 页的 PPT

### ⚠️ GPT 注意事项
- 中文回复时，偶尔会切换到英文 — 始终用用户语言回复
- 不要过度使用 markdown — 保持简洁
- 遇到工具错误，分析原因后换方案

### 🎨 文档创建
- PPT: 用 create_ppt 工具，支持 PptxGenJS 全部特性
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
- 大文件: write_file + 工具的 file 参数
""",

# ─── Gemini ─────────────────────────────────────────────────────────────
"gemini": """## 🎯 Gemini 模型专属优化策略

你运行在 **Gemini (Google)** 模型上。以下是关键优化规则：

### ⚡ Gemini 核心优势
- 多模态能力强 — 图片理解优秀
- 长上下文窗口 — 处理大量数据
- 代码生成能力强

### 📐 工具调用规范
- Gemini 工具调用有时会生成多余参数 — 只传必需参数
- 不要在 arguments 里传 None/null — 直接省略
- 确保 JSON 字符串正确转义

### ⚠️ Gemini 注意事项
- 有时会在工具调用前输出过多"思考" — 直接调用
- 中文回复质量有时不稳定 — 如果不确定，用简洁中文
- 复杂任务用 todo_create 分步

### 🎨 文档创建
- PPT: 用 create_ppt 工具（PptxGenJS），不要用 python-pptx
- **PPT 动画**: 用 animate_ppt 工具，不要自己写 Python 脚本拼 XML
- Word/Excel: 用专用工具
- 不要用 execute_code 自己写 Office 文件
""",

# ─── Qwen (通义千问) ───────────────────────────────────────────────────
"qwen": """## 🎯 Qwen 模型专属优化策略

你运行在 **Qwen (通义千问, 阿里)** 模型上。以下是关键优化规则：

### ⚡ Qwen 核心优势
- 中文理解顶尖 — 直接用中文交互
- 工具调用稳定 — 支持标准 function calling
- 长文本处理好

### 📐 工具调用规范
- Qwen 工具调用格式稳定
- 参数尽量简洁，单次不超过 5KB
- slides_file 用于 >5 页的 PPT

### ⚠️ Qwen 注意事项
- 有时会生成过于"客气"的回复 — 直接干活，少客套
- 复杂任务先 todo_create 分步
- 工具失败后看错误信息换方案，不要重试超过 2 次

### 🎨 文档创建
- PPT: 用 create_ppt 工具（PptxGenJS）
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
- 大数据: write_file 写文件 → 工具读文件
""",

# ─── Llama (Meta) ──────────────────────────────────────────────────────
"llama": """## 🎯 Llama 模型专属优化策略

你运行在 **Llama (Meta)** 模型上。以下是关键优化规则：

### ⚡ Llama 核心特性
- 开源模型，本地部署常见
- 工具调用需要更明确的指引
- 中文能力因版本差异较大

### 📐 工具调用规范
- Llama 工具调用格式可能不够稳定 — 如果调用失败，检查 JSON 格式
- 参数必须极简 — Llama 对长参数敏感
- slides_file 用于 >5 页的 PPT（必须用文件方式）

### ⚠️ Llama 注意事项
- JSON 截断风险较高 — 参数越短越好
- 不要一次处理太多任务 — 用 todo_create 分步
- 工具失败 2 次后必须换方案
- 优先用 write_file 写数据文件，再传文件路径给工具

### 🎨 文档创建
- PPT: 用 create_ppt 工具，必须用 slides_file
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
- 不要用 execute_code 自己写 Office 文件
""",

# ─── Mistral ────────────────────────────────────────────────────────────
"mistral": """## 🎯 Mistral 模型专属优化策略

你运行在 **Mistral** 模型上。以下是关键优化规则：

### 📐 工具调用规范
- Mistral 工具调用格式稳定
- 参数简洁，单次不超过 5KB
- slides_file 用于 >5 页的 PPT

### ⚠️ Mistral 注意事项
- 直接调用工具，少分析
- 复杂任务用 todo_create 分步
- 工具失败后换方案，不重试超过 2 次

### 🎨 文档创建
- PPT: 用 create_ppt 工具
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",

# ─── GLM (智谱) ────────────────────────────────────────────────────────
"glm": """## 🎯 GLM 模型专属优化策略

你运行在 **GLM (智谱)** 模型上。以下是关键优化规则：

### ⚡ GLM 核心特性
- 中文理解优秀
- 工具调用支持标准格式

### 📐 工具调用规范
- 参数简洁，单次不超过 5KB
- slides_file 用于 >5 页的 PPT

### ⚠️ GLM 注意事项
- 直接调用工具，少客套
- 复杂任务用 todo_create 分步
- JSON 参数确保格式合法

### 🎨 文档创建
- PPT: 用 create_ppt 工具
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",

# ─── Moonshot / Kimi ───────────────────────────────────────────────────
"moonshot": """## 🎯 Moonshot/Kimi 模型专属优化策略

你运行在 **Moonshot/Kimi** 模型上。以下是关键优化规则：

### ⚡ 核心特性
- 长文本能力强
- 中文理解优秀

### 📐 工具调用规范
- 参数简洁，单次不超过 5KB
- slides_file 用于 >5 页的 PPT

### ⚠️ 注意事项
- 直接调用工具
- 复杂任务用 todo_create 分步

### 🎨 文档创建
- PPT: 用 create_ppt 工具
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",

# ─── Grok (xAI) ────────────────────────────────────────────────────────
"grok": """## 🎯 Grok 模型专属优化策略

你运行在 **Grok (xAI)** 模型上。以下是关键优化规则：

### 📐 工具调用规范
- 参数简洁
- slides_file 用于 >5 页的 PPT

### ⚠️ 注意事项
- 直接调用工具，少分析
- 复杂任务用 todo_create 分步

### 🎨 文档创建
- PPT: 用 create_ppt 工具
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",

# ─── MiniMax ───────────────────────────────────────────────────────────
"minimax": """## 🎯 MiniMax 模型专属优化策略

你运行在 **MiniMax** 模型上。以下是关键优化规则：

### 📐 工具调用规范
- MiniMax 支持 OpenAI 兼容的 function calling
- 参数简洁，单次不超过 5KB
- slides_file 用于 >5 页的 PPT

### ⚠️ 注意事项
- 直接调用工具，少分析
- 复杂任务用 todo_create 分步
- 工具失败 2 次后换方案

### 🎨 文档创建
- PPT: 用 create_ppt 工具
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",

# ─── Step (StepFun) ────────────────────────────────────────────────────
"step": """## 🎯 Step 模型专属优化策略

你运行在 **Step (StepFun)** 模型上。以下是关键优化规则：

### 📐 工具调用规范
- 参数简洁，单次不超过 5KB
- slides_file 用于 >5 页的 PPT

### ⚠️ 注意事项
- 直接调用工具，少分析
- 复杂任务用 todo_create 分步

### 🎨 文档创建
- PPT: 用 create_ppt 工具
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",

# ─── Phi (Microsoft) ──────────────────────────────────────────────────
"phi": """## 🎯 Phi 模型专属优化策略

你运行在 **Phi (Microsoft)** 模型上。以下是关键优化规则：

### ⚡ Phi 核心特性
- 轻量高效模型，适合快速任务
- 工具调用能力因版本差异

### 📐 工具调用规范
- 参数必须极简 — Phi 对长参数敏感
- slides_file 用于 >3 页的 PPT（必须用文件方式）
- 不要在 tool_call 的 arguments 里写大段 JSON

### ⚠️ 注意事项
- JSON 截断风险较高 — 参数越短越好
- 不要一次处理太多任务 — 用 todo_create 分步
- 工具失败 2 次后必须换方案

### 🎨 文档创建
- PPT: 用 create_ppt 工具，必须用 slides_file
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",

# ─── Solar (Upstage) ──────────────────────────────────────────────────
"solar": """## 🎯 Solar 模型专属优化策略

你运行在 **Solar (Upstage)** 模型上。以下是关键优化规则：

### 📐 工具调用规范
- 参数简洁，单次不超过 5KB
- slides_file 用于 >5 页的 PPT

### ⚠️ 注意事项
- 直接调用工具，少分析
- 复杂任务用 todo_create 分步

### 🎨 文档创建
- PPT: 用 create_ppt 工具
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
- Word/Excel: 用专用工具
""",
}


# ═══════════════════════════════════════════════════════════════════════════
# HOT-UPDATE: Load .md files from model_profiles/ directory
# ═══════════════════════════════════════════════════════════════════════════

def _load_hot_profile(family: str) -> Optional[str]:
    """Load a hot-updatable .md profile for the given family.
    
    Looks for: model_profiles/{family}.md
    If found, returns its content (which OVERRIDES the hardcoded profile).
    """
    if not _PROFILES_DIR.is_dir():
        return None
    
    md_path = _PROFILES_DIR / f"{family}.md"
    if md_path.is_file():
        try:
            content = md_path.read_text(encoding="utf-8").strip()
            if content:
                logger.info("Loaded hot-update profile: %s", md_path)
                return content
        except Exception as e:
            logger.warning("Failed to load hot profile %s: %s", md_path, e)
    return None


def _load_hot_profile_extra(family: str) -> Optional[str]:
    """Load EXTRA rules from model_profiles/{family}.extra.md
    
    This is APPENDED to the hardcoded profile (extend, not override).
    Use this to add model-specific rules without replacing the hardcoded profile.
    """
    if not _PROFILES_DIR.is_dir():
        return None
    
    md_path = _PROFILES_DIR / f"{family}.extra.md"
    if md_path.is_file():
        try:
            content = md_path.read_text(encoding="utf-8").strip()
            if content:
                logger.info("Loaded hot-update extra profile: %s", md_path)
                return content
        except Exception as e:
            logger.warning("Failed to load hot extra profile %s: %s", md_path, e)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def get_model_profile(model_name: Optional[str]) -> str:
    """Get the model-specific system prompt profile.
    
    Resolution order:
    1. Hot-update .md file (OVERRIDE) — model_profiles/{family}.md
    2. Hardcoded profile — HARDCODED_PROFILES[family]
    3. Default fallback — generic guidance
    4. Hot-update extra .md file (APPEND) — model_profiles/{family}.extra.md
    
    Args:
        model_name: The model name from config or ChatMessage (e.g. "mimo-v2.5-pro")
    
    Returns:
        Model-specific profile string to append to system prompt.
        Empty string if no profile found (shouldn't happen — default is always returned).
    """
    family = detect_model_family(model_name)
    
    # 1. Try hot-update OVERRIDE
    hot = _load_hot_profile(family)
    if hot:
        extra = _load_hot_profile_extra(family)
        return hot + (f"\n\n{extra}" if extra else "")
    
    # 2. Try hardcoded profile
    hardcoded = HARDCODED_PROFILES.get(family)
    if hardcoded:
        extra = _load_hot_profile_extra(family)
        return hardcoded + (f"\n\n{extra}" if extra else "")
    
    # 3. Default fallback
    default = _load_hot_profile("default")
    if default:
        return default
    
    return _DEFAULT_PROFILE


_DEFAULT_PROFILE = """## 🎯 通用模型优化策略

### 📐 工具调用规范
- 工具参数必须是合法 JSON，字符串用双引号
- 不要在 arguments 里传默认值或空值 — 只传必需参数
- 参数单次不超过 5KB — 超过就用 write_file 写文件再传路径

### ⚠️ 通用注意事项
- 直接调用工具，不要先输出大段分析
- 复杂任务用 todo_create 分步跟踪
- 工具失败 2 次后换方案，不要重试超过 2 次
- 用 verify_file 验证文件创建成功

### 🎨 文档创建
- PPT: 用 create_ppt 工具（PptxGenJS），不要用 python-pptx
- **PPT 动画**: 用 animate_ppt 工具，不要自己写脚本拼 XML
  - ≤5页：直接传 slides 参数（必须用 elements 数组格式）
  - >5页：write_file("slides.json", [...]) → create_ppt(path, slides_file="slides.json")
- **PPT 动画**: 用 animate_ppt 工具（不要自己写 Python 脚本拼 XML！）
  1. list_ppt_shapes(path) 查看形状 ID
  2. animate_ppt(path, animations=[{slide, effect, target}]) 添加动画
  3. 支持 64 种动画 + 27 种幻灯片切换
- Word: 用 create_word 工具
- Excel: 用 create_excel / edit_excel 工具
- 不要用 execute_code 自己写 Office 文件 — 用专用工具
"""


def ensure_profiles_dir():
    """Create the model_profiles directory if it doesn't exist."""
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create a README if empty
    readme = _PROFILES_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Model Profiles (Hot-Update)\n\n"
            "Drop `.md` files here to override model-specific system prompts.\n\n"
            "## File naming\n"
            "- `{family}.md` — OVERRIDES the hardcoded profile for that family\n"
            "- `{family}.extra.md` — APPENDS to the hardcoded profile (extend, not replace)\n\n"
            "## Supported families\n"
            "mimo, deepseek, claude, gpt, gemini, qwen, llama, mistral, glm, moonshot, "
            "yi, internlm, grok, default\n\n"
            "## Example\n"
            "To add custom rules for MIMO without replacing the hardcoded profile:\n"
            "Create `mimo.extra.md` with your additional rules.\n",
            encoding="utf-8",
        )


# Auto-create on import
ensure_profiles_dir()
