"""
Email service for magic link authentication
Supports multiple email providers: Resend, SendGrid, Mailgun, SMTP
"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import requests
from config import settings

class EmailService:
    def __init__(self):
        self.service = settings.email_service.lower()
        self.api_key = settings.email_api_key
        self.from_email = settings.email_from
        self.from_name = settings.email_from_name
        self.enabled = settings.email_enabled

    def send_magic_link_email(self, to_email: str, magic_link: str) -> bool:
        """Send magic link email using configured service"""
        if not self.enabled:
            print(f"📧 Email disabled - Magic link for {to_email}: {magic_link}")
            return True

        subject = "🔗 Your secure login link"
        
        # Create email content
        html_content = self._create_magic_link_html(magic_link)
        text_content = self._create_magic_link_text(magic_link)
        
        try:
            if self.service == "resend":
                return self._send_via_resend(to_email, subject, html_content, text_content)
            elif self.service == "sendgrid":
                return self._send_via_sendgrid(to_email, subject, html_content, text_content)
            elif self.service == "mailgun":
                return self._send_via_mailgun(to_email, subject, html_content, text_content)
            elif self.service == "smtp":
                return self._send_via_smtp(to_email, subject, html_content, text_content)
            else:
                print(f"❌ Unknown email service: {self.service}")
                return False
                
        except Exception as e:
            print(f"❌ Email sending failed: {e}")
            return False

    def _send_via_resend(self, to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """Send email via Resend API"""
        if not self.api_key:
            print("❌ RESEND_API_KEY not configured")
            return False
            
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "from": f"{self.from_name} <{self.from_email}>",
            "to": [to_email],
            "subject": subject,
            "html": html_content,
            "text": text_content
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            print(f"✅ Magic link sent via Resend to {to_email}")
            return True
        else:
            print(f"❌ Resend API error: {response.status_code} - {response.text}")
            return False

    def _send_via_sendgrid(self, to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """Send email via SendGrid API"""
        if not self.api_key:
            print("❌ SENDGRID_API_KEY not configured")
            return False
            
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "personalizations": [{
                "to": [{"email": to_email}]
            }],
            "from": {
                "email": self.from_email,
                "name": self.from_name
            },
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_content},
                {"type": "text/html", "value": html_content}
            ]
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 202:
            print(f"✅ Magic link sent via SendGrid to {to_email}")
            return True
        else:
            print(f"❌ SendGrid API error: {response.status_code} - {response.text}")
            return False

    def _send_via_mailgun(self, to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """Send email via Mailgun API"""
        if not self.api_key:
            print("❌ MAILGUN_API_KEY not configured")
            return False
            
        # Extract domain from from_email
        domain = self.from_email.split('@')[1] if '@' in self.from_email else 'localhost'
        url = f"https://api.mailgun.net/v3/{domain}/messages"
        
        response = requests.post(
            url,
            auth=("api", self.api_key),
            data={
                "from": f"{self.from_name} <{self.from_email}>",
                "to": [to_email],
                "subject": subject,
                "text": text_content,
                "html": html_content
            }
        )
        
        if response.status_code == 200:
            print(f"✅ Magic link sent via Mailgun to {to_email}")
            return True
        else:
            print(f"❌ Mailgun API error: {response.status_code} - {response.text}")
            return False

    def _send_via_smtp(self, to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """Send email via SMTP"""
        if not all([settings.smtp_host, settings.smtp_username, settings.smtp_password]):
            print("❌ SMTP configuration incomplete")
            return False
            
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.from_name} <{self.from_email}>"
        msg['To'] = to_email
        
        # Create text and HTML parts
        text_part = MIMEText(text_content, 'plain')
        html_part = MIMEText(html_content, 'html')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Send email
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
        
        if settings.smtp_use_tls:
            server.starttls()
            
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Magic link sent via SMTP to {to_email}")
        return True

    def _create_magic_link_html(self, magic_link: str) -> str:
        """Create HTML email template for magic link"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Your secure login link</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ text-align: center; padding: 20px 0; border-bottom: 1px solid #eee; }}
                .logo {{ font-size: 24px; font-weight: bold; color: #3b82f6; }}
                .content {{ padding: 30px 0; }}
                .button {{ display: inline-block; padding: 12px 30px; background: #3b82f6; color: white; text-decoration: none; border-radius: 6px; font-weight: 500; }}
                .button:hover {{ background: #2563eb; }}
                .footer {{ padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; text-align: center; }}
                .security-note {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 15px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">🧠 Second Brain</div>
                </div>
                
                <div class="content">
                    <h2>Secure Login Request</h2>
                    <p>Click the button below to securely log in to your Second Brain account:</p>
                    
                    <p style="text-align: center; margin: 30px 0;">
                        <a href="{magic_link}" class="button">Sign In to Second Brain</a>
                    </p>
                    
                    <div class="security-note">
                        <strong>🔒 Security Note:</strong>
                        <ul style="margin: 10px 0; padding-left: 20px;">
                            <li>This link expires in <strong>15 minutes</strong></li>
                            <li>It can only be used <strong>once</strong></li>
                            <li>If you didn't request this, you can safely ignore this email</li>
                        </ul>
                    </div>
                    
                    <p style="font-size: 14px; color: #666;">
                        If the button doesn't work, copy and paste this link into your browser:<br>
                        <a href="{magic_link}" style="word-break: break-all;">{magic_link}</a>
                    </p>
                </div>
                
                <div class="footer">
                    <p>This email was sent from Second Brain. If you have questions, please contact support.</p>
                    <p>&copy; 2025 Second Brain. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

    def _create_magic_link_text(self, magic_link: str) -> str:
        """Create plain text email for magic link"""
        return f"""
🧠 Second Brain - Secure Login

Hi there!

Click the link below to securely log in to your Second Brain account:

{magic_link}

🔒 Security Information:
- This link expires in 15 minutes
- It can only be used once  
- If you didn't request this, you can safely ignore this email

If you have any questions, please contact support.

---
© 2025 Second Brain. All rights reserved.
        """

    def test_connection(self) -> bool:
        """Test email service connection"""
        if not self.enabled:
            print("📧 Email service is disabled")
            return True
            
        if self.service == "resend" and self.api_key:
            # Test Resend API key
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get("https://api.resend.com/domains", headers=headers)
            return response.status_code == 200
            
        elif self.service == "sendgrid" and self.api_key:
            # Test SendGrid API key  
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get("https://api.sendgrid.com/v3/user/profile", headers=headers)
            return response.status_code == 200
            
        elif self.service == "smtp":
            try:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.quit()
                return True
            except Exception:
                return False
                
        return False

# Global email service instance
email_service = EmailService()