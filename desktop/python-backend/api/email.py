"""Email API — 邮件配置、收发、测试"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List

logger = logging.getLogger("hermes-backend.email")
router = APIRouter()


class EmailConfig(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    use_ssl: Optional[bool] = None


class SendRequest(BaseModel):
    to: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    body: str = ""
    cc: Optional[str] = None
    bcc: Optional[str] = None
    html: bool = False
    attachments: Optional[List[str]] = None


@router.get("/api/email/config")
async def get_email_config():
    """获取邮件配置"""
    try:
        from email_tools import load_email_config
        config = load_email_config()
        if config.get("password"):
            config["password"] = "***"
        return config
    except ImportError:
        return {"error": "email_tools not available"}
    except Exception as e:
        logger.error("Failed to get email config: %s", e)
        return {"error": str(e)}


@router.put("/api/email/config")
async def update_email_config(body: EmailConfig):
    """保存邮件配置"""
    try:
        from email_tools import save_email_config
        data = body.model_dump(exclude_none=True)
        if data.get("password") == "***":
            data.pop("password")
        save_email_config(data)
        return {"success": True}
    except ImportError:
        raise HTTPException(status_code=500, detail="email_tools not available")
    except Exception as e:
        logger.error("Failed to save email config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/email/test")
async def test_email_connection(body: EmailConfig):
    """测试邮件连接"""
    try:
        from email_tools import read_emails, load_email_config
        config = load_email_config()
        result = read_emails(
            limit=1,
            email_addr=body.email or config.get("email", ""),
            password=body.password if body.password != "***" else config.get("password", ""),
            imap_server=body.imap_server or config.get("imap_server", ""),
            imap_port=body.imap_port or config.get("imap_port", 993),
        )
        return {"success": result.get("success", False), "error": result.get("error")}
    except ImportError:
        return {"success": False, "error": "email_tools not available"}
    except Exception as e:
        logger.error("Email test failed: %s", e)
        return {"success": False, "error": str(e)}


@router.get("/api/email/inbox")
async def get_inbox(limit: int = Query(default=20, ge=1, le=100), unread: bool = False, folder: str = Query(default="INBOX", pattern=r'^[a-zA-Z0-9_\-\. ]+$')):
    """获取收件箱"""
    try:
        from email_tools import read_emails
        result = read_emails(folder=folder, limit=limit, unread_only=unread)
        return result
    except ImportError:
        return {"emails": [], "error": "email_tools not available"}
    except Exception as e:
        logger.error("Failed to get inbox: %s", e)
        return {"emails": [], "error": str(e)}


@router.get("/api/email/detail/{uid}")
async def get_email_detail(uid: str, folder: str = Query(default="INBOX", pattern=r'^[a-zA-Z0-9_\-\. ]+$')):
    """获取邮件详情"""
    try:
        from email_tools import read_email_detail
        return read_email_detail(uid=uid, folder=folder)
    except ImportError:
        return {"error": "email_tools not available"}
    except Exception as e:
        logger.error("Failed to get email detail: %s", e)
        return {"error": str(e)}


@router.post("/api/email/send")
async def send_email_api(body: SendRequest):
    """发送邮件"""
    try:
        from email_tools import send_email
        result = send_email(
            to=body.to, subject=body.subject, body=body.body,
            cc=body.cc, bcc=body.bcc, html=body.html,
            attachments=body.attachments if body.attachments else None,
        )
        return result
    except ImportError:
        return {"success": False, "error": "email_tools not available"}
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        return {"success": False, "error": str(e)}
