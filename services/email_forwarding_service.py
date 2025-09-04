"""
Email Forwarding Service - Handle email forwarding and processing for Second Brain
"""
import imaplib
import smtplib
import email
import re
import os
import json
import hashlib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from email.header import decode_header
from datetime import datetime
from typing import Optional, Dict, List, Any
import sqlite3

class EmailForwardingService:
    def __init__(self, get_conn_func):
        self.get_conn = get_conn_func
        
    def setup_email_forwarding(self, user_id: int, email_config: Dict[str, Any]) -> Dict[str, Any]:
        """Set up email forwarding for a user"""
        
        # Generate unique forwarding address
        forwarding_address = self._generate_forwarding_address(user_id)
        
        # Save email configuration
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        self.create_email_tables()
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_email_config 
            (user_id, forwarding_address, provider_config, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            forwarding_address,
            json.dumps(email_config),
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        
        return {
            'success': True,
            'forwarding_address': forwarding_address,
            'setup_instructions': self._get_setup_instructions(email_config.get('provider', 'gmail'))
        }
    
    def _generate_forwarding_address(self, user_id: int) -> str:
        """Generate unique forwarding email address for user"""
        # Create a unique identifier based on user_id and timestamp
        unique_id = hashlib.md5(f"{user_id}_{datetime.utcnow().timestamp()}".encode()).hexdigest()[:8]
        return f"capture-{user_id}-{unique_id}@secondbrain.local"
    
    def _get_setup_instructions(self, provider: str) -> Dict[str, Any]:
        """Get provider-specific setup instructions"""
        instructions = {
            'gmail': {
                'name': 'Gmail Setup',
                'steps': [
                    "Open Gmail settings (gear icon → Settings)",
                    "Go to 'Forwarding and POP/IMAP' tab",
                    "Click 'Add a forwarding address'",
                    "Enter your Second Brain forwarding address",
                    "Gmail will send a verification email - check your Second Brain dashboard",
                    "Once verified, choose 'Forward a copy' and select what to do with Gmail's copy",
                    "Optional: Create filters to forward only specific emails"
                ],
                'filters': [
                    "Create filters for specific senders (e.g., newsletters, work emails)",
                    "Filter by subject keywords (e.g., 'Invoice', 'Receipt', 'Important')",
                    "Use labels to organize forwarded emails before processing",
                    "Forward emails with attachments to capture documents automatically"
                ],
                'tips': [
                    "Use '+' addressing: yourname+brain@gmail.com forwards to Second Brain",
                    "Create a dedicated Gmail account just for forwarding",
                    "Set up vacation responders to auto-forward urgent emails"
                ]
            },
            'outlook': {
                'name': 'Outlook.com Setup',
                'steps': [
                    "Open Outlook.com settings (gear icon → View all settings)",
                    "Go to 'Mail' → 'Forwarding'",
                    "Enable forwarding toggle",
                    "Enter your Second Brain forwarding address",
                    "Choose whether to keep copies in Outlook",
                    "Save settings"
                ],
                'rules': [
                    "Go to Settings → Mail → Rules",
                    "Create rules to forward specific emails",
                    "Use conditions like sender, subject, or keywords",
                    "Set action to 'Forward to' your Second Brain address"
                ],
                'tips': [
                    "Use rules for more granular control than global forwarding",
                    "Forward calendar invites to capture meeting info",
                    "Set up forwarding for shared mailboxes"
                ]
            },
            'apple': {
                'name': 'Apple Mail Setup',
                'steps': [
                    "Open Mail app on Mac",
                    "Go to Mail → Preferences → Rules",
                    "Click 'Add Rule'",
                    "Set conditions (sender, subject, contains keywords, etc.)",
                    "Set action to 'Forward Message'",
                    "Enter your Second Brain forwarding address",
                    "Save the rule"
                ],
                'icloud': [
                    "Sign in to iCloud.com",
                    "Open Mail",
                    "Click gear icon → Rules",
                    "Create forwarding rules similar to Mac Mail"
                ],
                'tips': [
                    "Create multiple rules for different types of content",
                    "Use smart mailboxes to organize before forwarding",
                    "Forward VIP emails automatically to Second Brain"
                ]
            },
            'thunderbird': {
                'name': 'Thunderbird Setup',
                'steps': [
                    "Go to Tools → Message Filters",
                    "Click 'New...' to create a filter",
                    "Set filter criteria (sender, subject, etc.)",
                    "Choose 'Forward Message' action",
                    "Enter your Second Brain forwarding address",
                    "Save filter"
                ],
                'tips': [
                    "Use folder-based filters for organization",
                    "Set up filters for RSS feeds forwarding",
                    "Forward emails with specific attachments"
                ]
            }
        }
        
        return instructions.get(provider, instructions['gmail'])
    
    def process_forwarded_email(self, email_content: str, forwarding_address: str) -> Dict[str, Any]:
        """Process a forwarded email and save to Second Brain"""
        
        # Parse email
        msg = email.message_from_string(email_content)
        
        # Extract email data
        email_data = self._extract_email_data(msg)
        
        # Find user from forwarding address
        user_id = self._get_user_from_forwarding_address(forwarding_address)
        
        if not user_id:
            return {'success': False, 'error': 'Invalid forwarding address'}
        
        # Save to Second Brain using mobile capture service
        from services.mobile_capture_service import MobileCaptureService
        mobile_service = MobileCaptureService(self.get_conn)
        
        result = mobile_service.process_email_capture(user_id, email_data)
        
        # Log the processing
        self._log_email_processing(user_id, forwarding_address, email_data, result)
        
        return result
    
    def _extract_email_data(self, msg) -> Dict[str, Any]:
        """Extract structured data from email message"""
        
        # Extract basic fields
        subject = self._decode_header(msg.get('Subject', ''))
        sender = self._decode_header(msg.get('From', ''))
        date = msg.get('Date', '')
        
        # Extract body
        body_text = ""
        body_html = ""
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if "attachment" in content_disposition:
                    # Handle attachment
                    filename = part.get_filename()
                    if filename:
                        attachments.append({
                            'filename': filename,
                            'content_type': content_type,
                            'size': len(part.get_payload(decode=True) or b'')
                        })
                elif content_type == "text/plain":
                    body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                elif content_type == "text/html":
                    body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            # Single part message
            if msg.get_content_type() == "text/plain":
                body_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            elif msg.get_content_type() == "text/html":
                body_html = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        return {
            'subject': subject,
            'from': sender,
            'body': body_text,
            'html_body': body_html,
            'attachments': attachments,
            'received_date': date
        }
    
    def _decode_header(self, header: str) -> str:
        """Decode email header properly"""
        if not header:
            return ""
        
        decoded_parts = decode_header(header)
        decoded_string = ""
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    decoded_string += part.decode(encoding, errors='ignore')
                else:
                    decoded_string += part.decode('utf-8', errors='ignore')
            else:
                decoded_string += str(part)
        
        return decoded_string
    
    def _get_user_from_forwarding_address(self, forwarding_address: str) -> Optional[int]:
        """Get user ID from forwarding address"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id FROM user_email_config 
            WHERE forwarding_address = ? AND is_active = 1
        """, (forwarding_address,))
        
        result = cursor.fetchone()
        return result[0] if result else None
    
    def _log_email_processing(self, user_id: int, forwarding_address: str, email_data: Dict, result: Dict):
        """Log email processing for debugging and analytics"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO email_processing_log 
            (user_id, forwarding_address, sender, subject, note_id, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            forwarding_address,
            email_data.get('from', ''),
            email_data.get('subject', ''),
            result.get('note_id'),
            'success' if result.get('success') else 'error',
            result.get('error') if not result.get('success') else None
        ))
        
        conn.commit()
    
    def create_email_tables(self):
        """Create necessary database tables for email functionality"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # User email configuration table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_email_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                forwarding_address TEXT UNIQUE NOT NULL,
                provider_config TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Email processing log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_processing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                forwarding_address TEXT NOT NULL,
                sender TEXT,
                subject TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                note_id INTEGER,
                status TEXT DEFAULT 'processed',
                error_message TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE SET NULL
            )
        """)
        
        conn.commit()
    
    def get_user_forwarding_config(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's email forwarding configuration"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT forwarding_address, provider_config, is_active, created_at
            FROM user_email_config
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        
        result = cursor.fetchone()
        if result:
            return {
                'forwarding_address': result[0],
                'provider_config': json.loads(result[1]) if result[1] else {},
                'is_active': bool(result[2]),
                'created_at': result[3]
            }
        return None
    
    def get_email_processing_stats(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get email processing statistics for user"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Total emails processed
        cursor.execute("""
            SELECT COUNT(*) FROM email_processing_log
            WHERE user_id = ? AND processed_at >= datetime('now', '-{} days')
        """.format(days), (user_id,))
        total_processed = cursor.fetchone()[0]
        
        # Success rate
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful
            FROM email_processing_log
            WHERE user_id = ? AND processed_at >= datetime('now', '-{} days')
        """.format(days), (user_id,))
        
        stats = cursor.fetchone()
        success_rate = (stats[1] / stats[0] * 100) if stats[0] > 0 else 0
        
        # Top senders
        cursor.execute("""
            SELECT sender, COUNT(*) as count
            FROM email_processing_log
            WHERE user_id = ? AND processed_at >= datetime('now', '-{} days')
            GROUP BY sender
            ORDER BY count DESC
            LIMIT 5
        """.format(days), (user_id,))
        top_senders = [{'sender': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        return {
            'total_processed': total_processed,
            'success_rate': round(success_rate, 1),
            'top_senders': top_senders,
            'period_days': days
        }

class EmailWebhookProcessor:
    """Process emails from webhook providers like SendGrid, Mailgun, etc."""
    
    def __init__(self, get_conn_func):
        self.get_conn = get_conn_func
        self.forwarding_service = EmailForwardingService(get_conn_func)
    
    def process_sendgrid_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SendGrid inbound email webhook"""
        
        try:
            # Extract email data from SendGrid format
            email_data = {
                'subject': webhook_data.get('subject', ''),
                'from': webhook_data.get('from', ''),
                'body': webhook_data.get('text', ''),
                'html_body': webhook_data.get('html', ''),
                'attachments': self._process_sendgrid_attachments(webhook_data.get('attachments', [])),
                'received_date': webhook_data.get('date', '')
            }
            
            # Get forwarding address (usually in 'to' field)
            forwarding_address = webhook_data.get('to', '')
            
            # Process the email
            return self._process_webhook_email(email_data, forwarding_address)
            
        except Exception as e:
            return {'success': False, 'error': f'SendGrid processing failed: {str(e)}'}
    
    def process_mailgun_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process Mailgun inbound email webhook"""
        
        try:
            # Extract email data from Mailgun format
            email_data = {
                'subject': webhook_data.get('Subject', ''),
                'from': webhook_data.get('sender', ''),
                'body': webhook_data.get('body-plain', ''),
                'html_body': webhook_data.get('body-html', ''),
                'attachments': self._process_mailgun_attachments(webhook_data),
                'received_date': webhook_data.get('Date', '')
            }
            
            # Get forwarding address
            forwarding_address = webhook_data.get('recipient', '')
            
            return self._process_webhook_email(email_data, forwarding_address)
            
        except Exception as e:
            return {'success': False, 'error': f'Mailgun processing failed: {str(e)}'}
    
    def _process_webhook_email(self, email_data: Dict[str, Any], forwarding_address: str) -> Dict[str, Any]:
        """Common email processing logic for webhooks"""
        
        # Find user from forwarding address
        user_id = self.forwarding_service._get_user_from_forwarding_address(forwarding_address)
        
        if not user_id:
            return {'success': False, 'error': 'Invalid forwarding address'}
        
        # Process with mobile capture service
        from services.mobile_capture_service import MobileCaptureService
        mobile_service = MobileCaptureService(self.get_conn)
        
        result = mobile_service.process_email_capture(user_id, email_data)
        
        # Log the processing
        self.forwarding_service._log_email_processing(user_id, forwarding_address, email_data, result)
        
        return result
    
    def _process_sendgrid_attachments(self, attachments: List[Dict]) -> List[Dict]:
        """Process SendGrid attachment format"""
        processed = []
        for attachment in attachments:
            processed.append({
                'filename': attachment.get('filename', ''),
                'content_type': attachment.get('content-type', ''),
                'size': len(attachment.get('content', ''))
            })
        return processed
    
    def _process_mailgun_attachments(self, webhook_data: Dict[str, Any]) -> List[Dict]:
        """Process Mailgun attachment format"""
        processed = []
        attachment_count = int(webhook_data.get('attachment-count', 0))
        
        for i in range(1, attachment_count + 1):
            attachment_key = f'attachment-{i}'
            if attachment_key in webhook_data:
                processed.append({
                    'filename': webhook_data.get(f'attachment-{i}', 'unknown'),
                    'content_type': 'application/octet-stream',
                    'size': 0  # Size not typically provided in webhook
                })
        
        return processed