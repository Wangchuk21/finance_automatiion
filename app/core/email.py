"""Email service for sending notifications."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
) -> bool:
    """
    Send an email via SMTP.
    
    Returns True if sent successfully, False otherwise.
    """
    if not settings.SMTP_HOST or settings.SMTP_PASSWORD == "changeme":
        logger.warning("SMTP not configured, skipping email send")
        return False

    try:
        from_addr = settings.SMTP_FROM
        if "@" not in from_addr:
            from_addr = f"Finance Automation <{settings.SMTP_USER}>"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email

        if body_text:
            msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        # Port 465 uses implicit TLS (SMTPS); port 587 uses STARTTLS.
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
            server.starttls()

        with server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent to {to_email}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_welcome_email(
    to_email: str,
    username: str,
    temp_password: str,
    expires_at_hours: int = 48,
) -> bool:
    """Send welcome email with temporary password to new user."""
    subject = "Welcome to Finance Automation - Your Account Details"
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1F4FD8;">Welcome to Finance Automation</h2>
            
            <p>Hello <strong>{username}</strong>,</p>
            
            <p>Your account has been created by an administrator. Here are your login details:</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Username:</strong> {username}</p>
                <p><strong>Temporary Password:</strong> <code style="background: #fff; padding: 5px 10px; border-radius: 3px; font-size: 1.1em;">{temp_password}</code></p>
                <p><strong>Login URL:</strong> <a href="http://localhost:5174/login">http://localhost:5174/login</a></p>
            </div>
            
            <p style="color: #DC2626;"><strong>Important:</strong></p>
            <ul>
                <li>This temporary password expires in {expires_at_hours} hours</li>
                <li>You must change your password on first login</li>
                <li>Keep your credentials secure</li>
            </ul>
            
            <p>If you did not request this account, please contact your administrator.</p>
            
            <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
            <p style="color: #888; font-size: 0.9em;">
                This is an automated message from Finance Automation. Please do not reply.
            </p>
        </div>
    </body>
    </html>
    """
    
    body_text = f"""
Welcome to Finance Automation

Hello {username},

Your account has been created by an administrator. Here are your login details:

Username: {username}
Temporary Password: {temp_password}
Login URL: http://localhost:5174/login

Important:
- This temporary password expires in {expires_at_hours} hours
- You must change your password on first login
- Keep your credentials secure

If you did not request this account, please contact your administrator.

---
This is an automated message from Finance Automation. Please do not reply.
    """
    
    return send_email(to_email, subject, body_html, body_text)


def send_password_reset_email(
    to_email: str,
    username: str,
    temp_password: str,
    expires_at_hours: int = 48,
) -> bool:
    """Send password reset email with new temporary password."""
    subject = "Your Finance Automation Password Has Been Reset"
    
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1F4FD8;">Password Reset</h2>
            
            <p>Hello <strong>{username}</strong>,</p>
            
            <p>Your password has been reset by an administrator. Here are your new login details:</p>
            
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Username:</strong> {username}</p>
                <p><strong>New Temporary Password:</strong> <code style="background: #fff; padding: 5px 10px; border-radius: 3px; font-size: 1.1em;">{temp_password}</code></p>
                <p><strong>Login URL:</strong> <a href="http://localhost:5174/login">http://localhost:5174/login</a></p>
            </div>
            
            <p style="color: #DC2626;"><strong>Important:</strong></p>
            <ul>
                <li>This temporary password expires in {expires_at_hours} hours</li>
                <li>You must change your password on first login</li>
                <li>Your previous password no longer works</li>
            </ul>
            
            <p>If you did not request this reset, please contact your administrator immediately.</p>
            
            <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
            <p style="color: #888; font-size: 0.9em;">
                This is an automated message from Finance Automation. Please do not reply.
            </p>
        </div>
    </body>
    </html>
    """
    
    body_text = f"""
Password Reset - Finance Automation

Hello {username},

Your password has been reset by an administrator. Here are your new login details:

Username: {username}
New Temporary Password: {temp_password}
Login URL: http://localhost:5174/login

Important:
- This temporary password expires in {expires_at_hours} hours
- You must change your password on first login
- Your previous password no longer works

If you did not request this reset, please contact your administrator immediately.

---
This is an automated message from Finance Automation. Please do not reply.
    """
    
    return send_email(to_email, subject, body_html, body_text)