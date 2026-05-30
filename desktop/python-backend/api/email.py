"""
Email API — 收发邮件、配置管理
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("hermes-backend.email")
router = APIRouter()


class EmailConfig(BaseModel):
    email: str = ""
    password: str = ""
    imap_server: str = ""
    imap_port: int = 993
    smtp_server: str = ""
    smtp_port: int = 465
    smtp_ssl: bool = True


class SendRequest(BaseModel):
    to: str  # 逗号分隔的邮箱列表
    subject: str
    body: str
    cc: str = ""
    bcc: str = ""
    html: bool = False
    attachments: list[str] = []

    def model_post_init(self, __context):
        # 验证收件人格式
        import re
        for addr in [self.to] + ([self.cc] if self.cc else []) + ([self.bcc] if self.bcc else []):
            for a in addr.split(","):
                a = a.strip()
                if a and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', a):
                    raise ValueError(f"无效邮箱地址: {a}")


@router.get("/api/email/config")
async def get_email_config():
    """获取邮件配置"""
    try:
        from email_tools import load_email_config
        config = load_email_config()
        # 隐藏密码
        if config.get("password"):
            config["password"] = "***"
        return config
    except ImportError:
        return {"error": "email_tools not available"}


@router.put("/api/email/config")
async def update_email_config(body: EmailConfig):
    """保存邮件配置"""
    try:
        from email_tools import save_email_config
        data = body.model_dump(exclude_none=True)
        # 不覆盖密码为 *** 的情况
        if data.get("password") == "***":
            data.pop("password")
        save_email_config(data)
        return {"success": True}
    except ImportError:
        raise HTTPException(status_code=500, detail="email_tools not available")


@router.post("/api/email/test")
async def test_email_connection(body: EmailConfig):
    """测试邮件连接"""
    try:
        from email_tools import read_emails, load_email_config
        config = load_email_config()
        # 使用新配置测试
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


@router.get("/api/email/inbox")
async def get_inbox(limit: int = Query(default=20, ge=1, le=100), unread: bool = False, folder: str = Query(default="INBOX", pattern=r'^[a-zA-Z0-9_\-\. ]+$')):
    """获取收件箱"""
    try:
        from email_tools import read_emails
        result = read_emails(folder=folder, limit=limit, unread_only=unread)
        return result
    except ImportError:
        return {"emails": [], "error": "email_tools not available"}


@router.get("/api/email/detail/{uid}")
async def get_email_detail(uid: str, folder: str = "INBOX"):
    """获取邮件详情"""
    try:
        from email_tools import read_email_detail
        return read_email_detail(uid=uid, folder=folder)
    except ImportError:
        return {"error": "email_tools not available"}


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
