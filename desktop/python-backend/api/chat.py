"""Hermes Desktop Python Backend — FastAPI server with tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.session_manager import SessionManager
from api.memory import MemoryManager
from tools import all_tools, openai_tools, execute_tool

logger = logging.getLogger("hermes-backend")

# ─── Constants ─────────────────────────────────────────────────────────────

MAX_CONTENT_LENGTH = 100_000  # 100KB max message
MAX_INPUT_TOKENS = 128_000
DEFAULT_MAX_TOKENS = 4096
SESSION_TIMEOUT = 3600  # 1 hour

# ─── System Prompt ─────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are Hermes, an AI desktop assistant with FULL tool access. You MUST use tools to complete tasks — NEVER just describe what you would do.

## CRITICAL RULES
1. **ACT, don't describe** — When user asks to create/modify/search something, call the tool IMMEDIATELY. Do NOT say "I can help you with that" or "Would you like me to..." — just DO IT.
2. **Maintain context** — Remember what was discussed. If user says "1" or "yes" or "ok", refer to the previous offer/question.
3. **No unnecessary questions** — If user says "make a PPT about X", make it directly with reasonable defaults. Don't ask for style/length/format unless truly ambiguous.
4. **NEVER say you can't do something** — You have tools. Use them. If user asks for a PPT, create it. If they ask to search, search. If they ask to run code, run it.
5. **Maintain conversation state** — Keep track of what you've done. If you created a file, remember the path. If you searched something, remember the results.

## AVAILABLE TOOLS
### File Operations
- **read_file** — Read file contents with line numbers
- **write_file** — Create/overwrite any file (.py, .md, .pptx, .docx, .xlsx, .html, etc.)
- **search_files** — Search for files by name or content patterns
- **list_files** — List directory contents

### System Operations
- **terminal** — Run shell commands (python scripts, pip install, system commands)

### Web Operations
- **web_search** — Search the internet (DuckDuckGo)
- **web_extract** — Extract and read content from URLs

### Vision & Screen
- **screen_capture** — Take screenshots of the current screen
  - Parameters: region ('full', 'active_window', or 'x,y,width,height'), save_path
  - Use this BEFORE vision_locate to get an image to analyze
- **vision_locate** — Analyze screenshots to locate GUI elements or understand screen content
  - Parameters: image_path (required), question (what to find/understand)
  - Uses nvidia/LocateAnything-3B model for visual understanding
  - Can identify buttons, text, icons, layout, and other UI elements
- **ocr_extract** — Extract text from images using OCR
  - Parameters: image_path (required), language ('chi_sim', 'eng', 'chi_sim+eng'), method ('tesseract' or 'vision')
  - Use 'vision' method for complex layouts or handwritten text

## YOUR CAPABILITIES
You CAN do all of these by writing Python scripts and running them:
- **PPT Creation** — python-pptx library is installed. Write a .py script, run it, deliver the .pptx file
- **Word Documents** — python-docx library is installed
- **Excel Spreadsheets** — openpyxl library is installed
- **Image Processing** — Pillow library is installed (resize, crop, filters, format conversion)
- **Web Scraping** — Use web_search and web_extract tools
- **File Operations** — Read, write, search any file
- **Code Execution** — Run any Python script via terminal tool
- **Screen Automation** — pyautogui is installed (mouse, keyboard control)
- **Visual Understanding** — Use screen_capture + vision_locate to see and understand screen content
- **OCR Text Extraction** — Use ocr_extract to read text from images, screenshots, or scanned documents

## SCREEN AUTOMATION WORKFLOW
To interact with GUI elements:
1. Take a screenshot: screen_capture(region='full')
2. Find the element: vision_locate(image_path='...', question='find the login button')
3. Use the coordinates from vision_locate result with pyautogui to click/type

## HOW TO CREATE PPT
1. Write a Python script using python-pptx
2. Run it with terminal tool
3. Tell user the output file path
Example: User says "make a PPT about apples" → write apple_ppt.py → run it → "Created: apple_report.pptx"

## HOW TO CREATE WORD/EXCEL
Same pattern: write Python script → run it → deliver file

## CONTEXT & MEMORY
You have persistent memory. Previous conversations and user preferences are injected into your context. Use this knowledge to provide better, personalized responses.

Respond in the user's language. Be concise. Always use tools to complete tasks."""


class ChatMessage(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_LENGTH)
    session_id: Optional[str] = None
    model: Optional[str] = "default"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    system_prompt: Optional[str] = None
    thinking_mode: Optional[str] = None
    thinking_budget: Optional[int] = None
    proxy_url: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)


class SessionCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


# ─── App Setup ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    logger.info("Hermes Desktop Backend starting...")
    yield
    logger.info("Hermes Desktop Backend shutting down...")


app = FastAPI(
    title="Hermes Desktop Backend",
    version="1.9.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Managers ──────────────────────────────────────────────────────────────

session_manager = SessionManager()
memory_manager = MemoryManager()


# ─── Helper Functions ──────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars for English, 2 chars for Chinese."""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars + (other_chars // 4) + 1


def get_model_context_config(model: str) -> tuple[int, int]:
    """Get context window and max response tokens for a model."""
    model_lower = model.lower()

    # MIMO models
    if "mimo" in model_lower:
        return 1_000_000, 32_000

    # Claude models
    if "claude" in model_lower:
        if "opus" in model_lower:
            return 200_000, 4096
        return 200_000, 4096

    # GPT models
    if "gpt-4" in model_lower:
        return 128_000, 4096
    if "gpt-3.5" in model_lower:
        return 16_385, 4096

    # Default
    return 32_768, 4096


def trim_messages(messages: list[dict], max_input_tokens: int) -> list[dict]:
    """Trim message history to fit within token limit, preserving system prompt and recent messages."""
    if not messages:
        return messages

    # Always keep the first message (system prompt or first user message)
    result = [messages[0]]
    total_tokens = estimate_tokens(messages[0].get("content", ""))

    # Work backwards from most recent messages
    for msg in reversed(messages[1:]):
        msg_tokens = 0
        if "content" in msg and msg["content"]:
            msg_tokens += estimate_tokens(msg["content"])
        if "tool_calls" in msg:
            msg_tokens += estimate_tokens(json.dumps(msg["tool_calls"]))
        if total_tokens + msg_tokens > max_input_tokens and result:
            break
        result.append(msg)
        total_tokens += msg_tokens

    result.reverse()
    return result


# ─── API Routes ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "version": "1.9.0",
        "tools_count": len(all_tools()),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/tools")
async def list_tools():
    """List all available tools."""
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in all_tools()
        ]
    }


@app.post("/chat")
async def chat(message: ChatMessage):
    """Process a chat message with tool support."""
    session_id = message.session_id or str(int(time.time() * 1000))

    # Get or create session
    session = session_manager.get_session(session_id)
    if not session:
        session = session_manager.create_session(session_id)
        logger.info("Created new session: %s", session_id)

    # Add user message to history
    session["messages"].append({
        "role": "user",
        "content": message.content,
    })

    # Build message history with model-aware context window
    history = session["messages"]
    api_messages = []

    # System prompt with memory context
    sys_prompt = message.system_prompt or DEFAULT_SYSTEM_PROMPT
    memory_ctx = get_memory_context()
    if memory_ctx:
        sys_prompt = sys_prompt + memory_ctx
    api_messages.append({"role": "system", "content": sys_prompt})

    # Auto-adjust context based on model
    context_window, max_response = get_model_context_config(message.model or "default")
    # Reserve tokens: system prompt + response + safety margin
    system_tokens = estimate_tokens(sys_prompt)
    max_input_tokens = context_window - max_response - system_tokens - 500  # 500 token safety

    # Trim history to fit
    trimmed = trim_messages(history, max_input_tokens)
    api_messages.extend(trimmed)

    # Prepare API call
    base_url = message.base_url or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    api_key = message.api_key or os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        raise HTTPException(status_code=401, detail="API key not configured")

    # Call LLM
    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Prepare tools
        tools = openai_tools()

        payload = {
            "model": message.model or "gpt-3.5-turbo",
            "messages": api_messages,
            "max_tokens": message.max_tokens or max_response,
            "temperature": message.temperature if message.temperature is not None else 0.7,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Add proxy if specified
        client_kwargs = {"timeout": 120}
        if message.proxy_url:
            client_kwargs["proxy"] = message.proxy_url

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error("API error %d: %s", response.status_code, error_text[:500])
                raise HTTPException(status_code=response.status_code, detail=error_text)

            data = response.json()
            assistant_message = data["choices"][0]["message"]

            # Handle tool calls
            if "tool_calls" in assistant_message and assistant_message["tool_calls"]:
                # Add assistant message with tool calls
                session["messages"].append(assistant_message)

                # Execute each tool call
                for tool_call in assistant_message["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])

                    logger.info("Executing tool: %s(%s)", tool_name, tool_args)
                    result = await execute_tool(tool_name, tool_args)
                    logger.info("Tool result: %s...", result[:200])

                    # Add tool result to history
                    session["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })

                # Make a follow-up call to get final response
                api_messages_with_tools = [{"role": "system", "content": sys_prompt}]
                api_messages_with_tools.extend(trim_messages(session["messages"], max_input_tokens))

                payload["messages"] = api_messages_with_tools

                async with httpx.AsyncClient(**client_kwargs) as client2:
                    response2 = await client2.post(
                        f"{base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                    if response2.status_code == 200:
                        data2 = response2.json()
                        final_message = data2["choices"][0]["message"]
                        session["messages"].append(final_message)
                        return {
                            "response": final_message.get("content", ""),
                            "session_id": session_id,
                            "tool_calls": [
                                {
                                    "name": tc["function"]["name"],
                                    "arguments": json.loads(tc["function"]["arguments"]),
                                }
                                for tc in assistant_message["tool_calls"]
                            ],
                        }
                    else:
                        # Return tool results even if follow-up fails
                        return {
                            "response": f"Tools executed successfully but follow-up failed: {response2.text[:200]}",
                            "session_id": session_id,
                            "tool_calls": [
                                {
                                    "name": tc["function"]["name"],
                                    "arguments": json.loads(tc["function"]["arguments"]),
                                }
                                for tc in assistant_message["tool_calls"]
                            ],
                        }
            else:
                # No tool calls, just return the response
                session["messages"].append(assistant_message)
                return {
                    "response": assistant_message.get("content", ""),
                    "session_id": session_id,
                }

    except httpx.TimeoutException:
        logger.error("API request timed out")
        raise HTTPException(status_code=504, detail="API request timed out")
    except Exception as e:
        logger.error("Chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sessions")
async def create_session(request: SessionCreate):
    """Create a new chat session."""
    session_id = str(int(time.time() * 1000))
    session = session_manager.create_session(session_id, request.name)
    return {"session_id": session_id, "name": request.name}


@app.get("/sessions")
async def list_sessions():
    """List all sessions."""
    return {"sessions": session_manager.list_sessions()}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "messages": session["messages"],
        "created_at": session.get("created_at"),
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_manager.delete_session(session_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """Clear session history."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["messages"] = []
    return {"status": "cleared"}


# ─── Memory Endpoints ──────────────────────────────────────────────────────

@app.get("/memory")
async def get_memory():
    """Get all memories."""
    return {"memories": memory_manager.get_all()}


@app.post("/memory")
async def add_memory(request: dict):
    """Add a memory."""
    content = request.get("content")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    memory_manager.add(content)
    return {"status": "added"}


@app.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory."""
    if memory_manager.delete(memory_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Memory not found")


def get_memory_context() -> str:
    """Get memory context string to inject into system prompt."""
    memories = memory_manager.get_all()
    if not memories:
        return ""
    context = "\n\n## PERSISTENT MEMORY\nThings I remember about you:\n"
    for m in memories:
        context += f"- {m['content']}\n"
    return context


# ─── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        "api.chat:app",
        host="127.0.0.1",
        port=9876,
        reload=False,
        log_level="info",
    )
