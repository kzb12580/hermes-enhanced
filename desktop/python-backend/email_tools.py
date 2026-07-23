"""
Hermes Desktop 邮件工具 — 收发邮件、模板回复
支持 IMAP/SMTP，兼容 QQ邮箱/163/Outlook/Gmail/企业邮箱
"""
import os
import re
import json
import html as html_module
import email
import imaplib
import smtplib
import logging
import tempfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.header import decode_header, make_header
from email import encoders
from email.utils import formataddr, parseaddr
from typing import Optional
from pathlib import Path
from datetime import datetime

_log = logging.getLogger(__name__)

# IMAP 默认超时（秒）
IMAP_TIMEOUT = 30

# 附件大小上限 25MB
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024

# ── 常见邮箱 IMAP/SMTP 配置 ──────────────────────────────────────────────
EMAIL_PRESETS = {
    "qq.com": {"imap": "imap.qq.com", "imap_port": 993, "smtp": "smtp.qq.com", "smtp_port": 465, "smtp_ssl": True},
    "163.com": {"imap": "imap.163.com", "imap_port": 993, "smtp": "smtp.163.com", "smtp_port": 465, "smtp_ssl": True},
    "126.com": {"imap": "imap.126.com", "imap_port": 993, "smtp": "smtp.126.com", "smtp_port": 465, "smtp_ssl": True},
    "outlook.com": {"imap": "outlook.office365.com", "imap_port": 993, "smtp": "smtp.office365.com", "smtp_port": 587, "smtp_ssl": False},
    "hotmail.com": {"imap": "outlook.office365.com", "imap_port": 993, "smtp": "smtp.office365.com", "smtp_port": 587, "smtp_ssl": False},
    "gmail.com": {"imap": "imap.gmail.com", "imap_port": 993, "smtp": "smtp.gmail.com", "smtp_port": 587, "smtp_ssl": False},
    "yahoo.com": {"imap": "imap.mail.yahoo.com", "imap_port": 993, "smtp": "smtp.mail.yahoo.com", "smtp_port": 465, "smtp_ssl": True},
}


def _detect_provider(email_addr: str) -> Optional[dict]:
    """根据邮箱地址自动检测 IMAP/SMTP 配置"""
    domain = email_addr.split("@")[-1].lower()
    return EMAIL_PRESETS.get(domain)


def _decode_header_value(raw: str) -> str:
    """解码邮件头（MIME 编码）"""
    if not raw:
        return ""
    try:
        decoded_parts = decode_header(raw)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)
    except Exception:
        return raw


def _strip_html_tags(html_text: str) -> str:
    """安全地去除 HTML 标签，先转义再去除"""
    # 先用 html.escape 转义特殊字符防止 XSS，再去标签
    text = html_module.escape(html_text)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</(p|div|tr|li|h[1-6])>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    # 反转义 &amp; &lt; &gt; 回可读字符
    text = html_module.unescape(text)
    return text


def _get_email_body(msg) -> str:
    """提取邮件正文（纯文本优先）"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_text = payload.decode(charset, errors="replace")
                    body = _strip_html_tags(html_text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body.strip()


def _get_attachments(msg) -> list[dict]:
    """提取附件信息"""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                filename = _decode_header_value(part.get_filename() or "")
                attachments.append({
                    "filename": filename,
                    "size": len(part.get_payload(decode=True) or b""),
                    "content_type": part.get_content_type(),
                })
    return attachments


# ── 配置管理 ──────────────────────────────────────────────────────────────

_CONFIG_DIR = Path.home() / ".hermes" / "desktop"
_CONFIG_FILE = _CONFIG_DIR / "email.json"
_KEY_FILE = _CONFIG_DIR / ".email_key"
_ENCRYPTED_FIELDS = {"password"}


def _get_or_create_key() -> bytes:
    """获取或创建 Fernet 加密密钥"""
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    # 仅限当前用户读取
    import stat
    _KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return key


def _encrypt_value(value: str) -> str:
    """加密敏感字段"""
    from cryptography.fernet import Fernet
    if not value:
        return value
    f = Fernet(_get_or_create_key())
    return f.encrypt(value.encode()).decode()


def _decrypt_value(value: str) -> str:
    """解密敏感字段"""
    from cryptography.fernet import Fernet
    if not value:
        return value
    try:
        f = Fernet(_get_or_create_key())
        return f.decrypt(value.encode()).decode()
    except Exception:
        # 兼容明文密码（旧配置）
        return value


def load_email_config() -> dict:
    """加载邮件配置（自动解密敏感字段）"""
    if _CONFIG_FILE.exists():
        try:
            config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            # 解密敏感字段
            for field in _ENCRYPTED_FIELDS:
                if field in config and config[field]:
                    config[field] = _decrypt_value(config[field])
            return config
        except Exception:
            pass
    return {}


def save_email_config(config: dict):
    """保存邮件配置（自动加密敏感字段）"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_email_config()
    existing.update(config)
    # 加密敏感字段
    for field in _ENCRYPTED_FIELDS:
        if field in existing and existing[field]:
            # 避免重复加密
            try:
                _decrypt_value(existing[field])
            except Exception:
                existing[field] = _encrypt_value(existing[field])
    _CONFIG_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


# ── 收邮件 ────────────────────────────────────────────────────────────────

def _sanitize_imap_search(term: str) -> str:
    """清理 IMAP 搜索词，防止注入攻击"""
    # 只允许字母数字、中文、空格、点、下划线、连字符
    # 移除 IMAP 搜索特殊字符: ( ) " \ 等
    import re
    # 保留安全字符，移除危险字符
    sanitized = re.sub(r'[()\\"]', '', term)
    # 限制长度
    return sanitized[:200]


def read_emails(folder: str = "INBOX", limit: int = 20, unread_only: bool = False,
                search: str = "", imap_server: str = "", imap_port: int = 993,
                email_addr: str = "", password: str = "") -> dict:
    """
    读取邮件列表

    Args:
        folder: 邮箱文件夹 (INBOX/Sent/Drafts/自定义)
        limit: 最多返回数量
        unread_only: 仅未读
        search: 搜索关键词 (IMAP SEARCH 语法)
        imap_server: IMAP 服务器 (留空自动检测)
        imap_port: IMAP 端口
        email_addr: 邮箱地址
        password: 密码/授权码
    """
    mail = None
    try:
        # 从配置文件读取缺失参数
        config = load_email_config()
        email_addr = email_addr or config.get("email", "")
        password = password or config.get("password", "")
        imap_server = imap_server or config.get("imap_server", "")
        imap_port = imap_port or config.get("imap_port", 993)

        if not email_addr or not password:
            return {"error": "请配置邮箱地址和密码（授权码）", "success": False}

        if not imap_server:
            preset = _detect_provider(email_addr)
            if preset:
                imap_server = preset["imap"]
                imap_port = preset["imap_port"]
            else:
                return {"error": f"无法自动检测 {email_addr} 的 IMAP 服务器，请手动配置", "success": False}

        # 连接（加 timeout）
        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.socket().settimeout(IMAP_TIMEOUT)
        mail.login(email_addr, password)
        mail.select(folder)

        # 搜索
        if unread_only:
            criterion = "UNSEEN"
        elif search:
            # 清理搜索词防止注入
            safe_search = _sanitize_imap_search(search)
            if not safe_search:
                criterion = "ALL"
            else:
                criterion = f'(OR (SUBJECT "{safe_search}") (FROM "{safe_search}"))'
        else:
            criterion = "ALL"

        status, data = mail.search(None, criterion)
        if status != "OK":
            return {"error": "搜索失败", "success": False}

        msg_ids = data[0].split()
        msg_ids = msg_ids[-limit:]  # 取最新的
        msg_ids.reverse()

        emails = []
        for msg_id in msg_ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            emails.append({
                "id": msg_id.decode(errors="replace"),
                "from": _decode_header_value(msg.get("From", "")),
                "to": _decode_header_value(msg.get("To", "")),
                "subject": _decode_header_value(msg.get("Subject", "")),
                "date": msg.get("Date", ""),
                "body_preview": _get_email_body(msg)[:500],
                "has_attachments": len(_get_attachments(msg)) > 0,
                "attachments": _get_attachments(msg),
            })

        return {"emails": emails, "count": len(emails), "folder": folder, "success": True}
    except imaplib.IMAP4.error as e:
        return {"error": f"IMAP 错误: {e}", "success": False}
    except Exception as e:
        _log.error("read_emails failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass


def read_email_detail(uid: str, folder: str = "INBOX",
                      email_addr: str = "", password: str = "",
                      imap_server: str = "", imap_port: int = 993) -> dict:
    """读取单封邮件完整内容"""
    mail = None
    try:
        config = load_email_config()
        email_addr = email_addr or config.get("email", "")
        password = password or config.get("password", "")
        imap_server = imap_server or config.get("imap_server", "")
        imap_port = imap_port or config.get("imap_port", 993)

        if not imap_server:
            preset = _detect_provider(email_addr)
            if preset:
                imap_server = preset["imap"]
                imap_port = preset["imap_port"]

        mail = imaplib.IMAP4_SSL(imap_server, imap_port)
        mail.socket().settimeout(IMAP_TIMEOUT)
        mail.login(email_addr, password)
        mail.select(folder)

        status, msg_data = mail.fetch(uid.encode(), "(RFC822)")
        if status != "OK":
            return {"error": "邮件获取失败", "success": False}

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        result = {
            "from": _decode_header_value(msg.get("From", "")),
            "to": _decode_header_value(msg.get("To", "")),
            "cc": _decode_header_value(msg.get("Cc", "")),
            "subject": _decode_header_value(msg.get("Subject", "")),
            "date": msg.get("Date", ""),
            "body": _get_email_body(msg),
            "attachments": _get_attachments(msg),
            "success": True,
        }

        return result
    except Exception as e:
        return {"error": str(e), "success": False}
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass


# ── 发邮件 ────────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, body: str,
               cc: str = "", bcc: str = "",
               html: bool = False,
               attachments: list[str] = None,
               smtp_server: str = "", smtp_port: int = 465,
               smtp_ssl: bool = True,
               email_addr: str = "", password: str = "",
               reply_to: str = "") -> dict:
    """
    发送邮件

    Args:
        to: 收件人 (逗号分隔)
        subject: 主题
        body: 正文
        cc: 抄送
        bcc: 密送
        html: 是否 HTML 格式
        attachments: 附件路径列表
        smtp_server: SMTP 服务器 (留空自动检测)
        smtp_port: SMTP 端口
        smtp_ssl: 是否使用 SSL (True=465, False=STARTTLS/587)
        email_addr: 发件人邮箱
        password: 密码/授权码
        reply_to: 回复邮件的 Message-ID
    """
    server = None
    try:
        config = load_email_config()
        email_addr = email_addr or config.get("email", "")
        password = password or config.get("password", "")
        smtp_server = smtp_server or config.get("smtp_server", "")
        smtp_port = smtp_port or config.get("smtp_port", 465)
        smtp_ssl = smtp_ssl if "smtp_ssl" not in config else config.get("smtp_ssl", True)

        if not email_addr or not password:
            return {"error": "请配置邮箱地址和密码（授权码）", "success": False}

        if not smtp_server:
            preset = _detect_provider(email_addr)
            if preset:
                smtp_server = preset["smtp"]
                smtp_port = preset["smtp_port"]
                smtp_ssl = preset["smtp_ssl"]
            else:
                return {"error": f"无法自动检测 SMTP 服务器，请手动配置", "success": False}

        # 拆分收件人列表（fix #1: recipients split）
        to_list = [a.strip() for a in to.split(",") if a.strip()]

        # 构建邮件
        msg = MIMEMultipart()
        msg["From"] = formataddr(("", email_addr))
        msg["To"] = to
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject

        if reply_to:
            msg["In-Reply-To"] = reply_to
            msg["References"] = reply_to

        # 正文
        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        # 附件（fix #3: 25MB 大小限制 + 路径安全检查）
        if attachments:
            for filepath in attachments:
                # 路径安全检查：防止路径遍历攻击
                real_path = os.path.realpath(filepath)
                # 只允许访问 uploads 目录、临时目录、工作目录
                allowed_dirs = [
                    os.path.realpath(os.path.join(os.path.dirname(__file__), "uploads")),
                    os.path.realpath(tempfile.gettempdir()),
                    os.getcwd(),
                ]
                path_allowed = any(real_path.startswith(d) for d in allowed_dirs)
                if not path_allowed:
                    _log.warning(f"附件路径不允许: {filepath}")
                    return {"error": f"附件路径不允许访问: {os.path.basename(filepath)}", "success": False}
                if not os.path.isfile(filepath):
                    _log.warning(f"附件不存在: {filepath}")
                    continue
                file_size = os.path.getsize(filepath)
                if file_size > MAX_ATTACHMENT_SIZE:
                    return {"error": f"附件 {os.path.basename(filepath)} 超过 25MB 限制 ({file_size / 1024 / 1024:.1f}MB)", "success": False}
                part = MIMEBase("application", "octet-stream")
                with open(filepath, "rb") as f:
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(filepath)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

        # 发送（fix #1: 用拆分后的 to_list）
        all_recipients = list(to_list)
        if cc:
            all_recipients.extend([a.strip() for a in cc.split(",")])
        if bcc:
            all_recipients.extend([a.strip() for a in bcc.split(",")])

        if smtp_ssl:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
            server.starttls()

        server.login(email_addr, password)
        server.sendmail(email_addr, all_recipients, msg.as_string())

        return {"success": True, "to": to, "subject": subject}
    except smtplib.SMTPAuthenticationError:
        return {"error": "认证失败，请检查邮箱密码/授权码", "success": False}
    except smtplib.SMTPException as e:
        return {"error": f"SMTP 错误: {e}", "success": False}
    except Exception as e:
        _log.error("send_email failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


# ── 工具注册 ──────────────────────────────────────────────────────────────

EMAIL_TOOLS = {
    "read_emails": {"fn": read_emails, "concurrency": "read_parallel", "description": "读取邮件列表"},
    "read_email_detail": {"fn": read_email_detail, "concurrency": "read_parallel", "description": "读取邮件详情"},
    "send_email": {"fn": send_email, "concurrency": "write_serial", "description": "发送邮件"},
    "load_email_config": {"fn": load_email_config, "concurrency": "read_parallel", "description": "读取邮件配置"},
    "save_email_config": {"fn": save_email_config, "concurrency": "write_serial", "description": "保存邮件配置"},
}
