"""
SMTP email utility.
Compatible with Brevo SMTP, QQ Mail SMTP, Gmail SMTP.
- Port 465: implicit SSL (SMTP_SSL)
- Port 587: STARTTLS
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings


def send_email(to: str, subject: str, body_html: str) -> bool:
    """
    Send an HTML email via SMTP.
    If SMTP_HOST is not configured, prints to console (dev mode) and returns True.
    """
    if not settings.SMTP_HOST:
        print(f"[EMAIL DEV] To: {to}")
        print(f"[EMAIL DEV] Subject: {subject}")
        print(f"[EMAIL DEV] Body: {body_html}")
        return True

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
            server.ehlo()
            if settings.SMTP_USE_TLS:
                server.starttls()
                server.ehlo()

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(msg["From"], [to], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send to {to}: {e}")
        return False
