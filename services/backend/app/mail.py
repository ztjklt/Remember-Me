"""Replaceable email delivery for one-time login codes."""

import smtplib
import json
import os
from hashlib import sha256
from email.message import EmailMessage
from pathlib import Path

from .config import Settings


class Mailer:
    def __init__(self, settings: Settings) -> None:
        if settings.mail_backend == "smtp" and not settings.smtp_host:
            raise ValueError("REMEMBER_SMTP_HOST is required for SMTP login email")
        self.settings = settings
        self.messages: list[tuple[str, str]] = []

    def send_code(self, email: str, code: str) -> None:
        if self.settings.mail_backend == "memory":
            if self.settings.environment not in {"development", "test"}:
                raise ValueError("An SMTP mailer is required outside development/test")
            self.messages.append((email, code))
            if self.settings.environment == "development":
                mailbox = Path("var/dev-mailbox")
                mailbox.mkdir(mode=0o700, parents=True, exist_ok=True)
                destination = mailbox / f"{sha256(email.encode()).hexdigest()}.json"
                temporary = mailbox / f".{destination.name}.{os.getpid()}"
                temporary.write_text(json.dumps({"email": email, "code": code}), encoding="utf-8")
                temporary.chmod(0o600)
                temporary.replace(destination)
            return
        message = EmailMessage()
        message["Subject"] = "Remember Me 登录验证码"
        message["From"] = self.settings.smtp_from
        message["To"] = email
        message.set_content(f"你的验证码是 {code}。10 分钟内有效。如果不是你发起的请求，请忽略。")
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password or "")
            smtp.send_message(message)
