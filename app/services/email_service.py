"""
Email verification code service.

- 6-digit numeric code
- Code stored as SHA-256 hash (not plaintext)
- 10-minute expiry (configurable)
- 60-second resend interval (configurable)
- Max 5 sends per email per hour (configurable)
"""

import hashlib
import random
import datetime
from typing import Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.email import send_email
from app.database.models import EmailVerificationCode


def _hash_code(code: str) -> str:
    """Hash a verification code with SECRET_KEY as salt."""
    raw = f"{settings.SECRET_KEY}:{code}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    """Generate a 6-digit numeric verification code."""
    return f"{random.randint(0, 999999):06d}"


def send_verification_code(db: Session, email: str, purpose: str) -> Tuple[bool, str]:
    """
    Generate, persist (hashed), and send a verification code via email.
    Returns (success, message).
    """
    now = datetime.datetime.utcnow()

    # --- Rate limit: resend interval ---
    latest = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
        )
        .order_by(EmailVerificationCode.last_sent_at.desc())
        .first()
    )
    if latest and latest.last_sent_at:
        elapsed = (now - latest.last_sent_at).total_seconds()
        if elapsed < settings.EMAIL_CODE_RESEND_INTERVAL_SECONDS:
            wait = int(settings.EMAIL_CODE_RESEND_INTERVAL_SECONDS - elapsed)
            return False, f"发送太频繁，请 {wait} 秒后再试"

    # --- Rate limit: max per hour ---
    one_hour_ago = now - datetime.timedelta(hours=1)
    hour_count = (
        db.query(func.count(EmailVerificationCode.id))
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.created_at >= one_hour_ago,
        )
        .scalar()
    )
    if hour_count >= settings.EMAIL_CODE_MAX_PER_HOUR:
        return False, "发送次数过多，请 1 小时后再试"

    # --- Generate & persist ---
    code = _generate_code()
    record = EmailVerificationCode(
        email=email,
        code_hash=_hash_code(code),
        purpose=purpose,
        expires_at=now + datetime.timedelta(minutes=settings.EMAIL_CODE_EXPIRE_MINUTES),
        send_count=1,
        last_sent_at=now,
    )
    db.add(record)
    db.commit()

    # --- Send ---
    subject = f"【{settings.APP_NAME}】邮箱验证码"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px;">
        <h2 style="color:#0d6efd;">{settings.APP_NAME}</h2>
        <p>您的验证码为：</p>
        <p style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#333;">{code}</p>
        <p>验证码 {settings.EMAIL_CODE_EXPIRE_MINUTES} 分钟内有效，请尽快使用。</p>
        <hr style="border:none;border-top:1px solid #eee;">
        <p style="font-size:12px;color:#999;">如果您没有请求此验证码，请忽略此邮件。</p>
    </div>
    """
    ok = send_email(email, subject, body)
    if not ok:
        return False, "邮件发送失败，请检查邮箱地址或稍后重试"

    # Dev mode: log code to console for testing
    if not settings.SMTP_HOST:
        print(f"[DEV] Verification code for {email}: {code}")

    return True, "验证码已发送，请查收邮件"


def verify_code(db: Session, email: str, code: str, purpose: str) -> Tuple[bool, str]:
    """
    Verify a submitted code against the hashed record.
    On success, marks the code as used and returns (True, "").
    """
    now = datetime.datetime.utcnow()
    code_hash = _hash_code(code)

    record = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.code_hash == code_hash,
            EmailVerificationCode.used_at.is_(None),
            EmailVerificationCode.expires_at > now,
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .first()
    )
    if not record:
        return False, "验证码错误或已过期"

    record.used_at = now
    db.commit()
    return True, ""
