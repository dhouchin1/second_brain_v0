"""
Mobile Capture Service - Handles all mobile input methods including iOS Shortcuts, 
email forwarding, SMS capture, and voice note processing.
"""
import json
import re
import email
import base64
from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
import sqlite3
from urllib.parse import unquote_plus
import hashlib
import uuid

class MobileCaptureService:
    def __init__(self, get_conn_func):
        self.get_conn = get_conn_func

    # === Apple Shortcuts Integration ===
    # Note: Apple Shortcuts processing is handled by the dedicated AppleShortcutsService
    # This service focuses on other mobile capture methods (email, SMS, voice)

    # === Email Processing ===
    
    def process_email_capture(self, user_id: int, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process emails forwarded to Second Brain"""
        subject = email_data.get('subject', 'No Subject')
        sender = email_data.get('from', '')
        body = email_data.get('body', '')
        attachments = email_data.get('attachments', [])
        html_body = email_data.get('html_body', '')
        
        # Clean and format email content
        processed_content = self._process_email_content(subject, sender, body, html_body, attachments)
        
        # Generate tags
        tags = self._generate_email_tags(subject, sender, body)
        
        # Save note
        note_id = self._save_mobile_note(
            user_id=user_id,
            content=processed_content['content'],
            title=processed_content['title'],
            tags=tags,
            note_type='email',
            metadata={
                'capture_method': 'email_forward',
                'sender': sender,
                'subject': subject,
                'has_attachments': len(attachments) > 0,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
        
        return {
            'success': True,
            'note_id': note_id,
            'processed_content': processed_content,
            'tags': tags,
            'capture_method': 'email_forward'
        }

    def _process_email_content(self, subject: str, sender: str, body: str, html_body: str, attachments: List[Dict]) -> Dict[str, Any]:
        """Process and format email content"""
        formatted_content = f"# 📧 {subject}\n\n"
        formatted_content += f"**From**: {sender}\n"
        formatted_content += f"**Received**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if attachments:
            formatted_content += f"**Attachments**: {len(attachments)} file(s)\n"
            for attachment in attachments:
                formatted_content += f"  - {attachment.get('filename', 'Unknown')}\n"
        
        formatted_content += "\n---\n\n"
        
        # Use HTML body if available and more substantial
        if html_body and len(html_body.strip()) > len(body.strip()):
            # Convert basic HTML to markdown
            clean_body = self._html_to_markdown(html_body)
            formatted_content += clean_body
        else:
            formatted_content += body
        
        return {
            'title': f"Email: {subject[:50]}{'...' if len(subject) > 50 else ''}",
            'content': formatted_content
        }

    def _html_to_markdown(self, html_content: str) -> str:
        """Convert basic HTML to markdown"""
        # Simple HTML to markdown conversion
        content = html_content
        
        # Replace common HTML tags
        content = re.sub(r'<br\s*/?>', '\n', content, flags=re.IGNORECASE)
        content = re.sub(r'<p[^>]*>', '\n\n', content, flags=re.IGNORECASE)
        content = re.sub(r'</p>', '', content, flags=re.IGNORECASE)
        content = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'[\2](\1)', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', content, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove remaining HTML tags
        content = re.sub(r'<[^>]+>', '', content)
        
        # Clean up excessive whitespace
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        content = content.strip()
        
        return content

    # === SMS/Text Processing ===
    
    def process_sms_capture(self, user_id: int, sms_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process SMS/text messages sent to Second Brain"""
        message_body = sms_data.get('body', '')
        sender = sms_data.get('sender', '')
        timestamp = sms_data.get('timestamp', datetime.utcnow().isoformat())
        
        # Parse message for special commands
        processed_content = self._process_sms_content(message_body, sender)
        
        # Generate tags
        tags = self._generate_sms_tags(message_body, sender)
        
        # Save note
        note_id = self._save_mobile_note(
            user_id=user_id,
            content=processed_content['content'],
            title=processed_content['title'],
            tags=tags,
            note_type='sms',
            metadata={
                'capture_method': 'sms',
                'sender': sender,
                'original_message': message_body,
                'timestamp': timestamp
            }
        )
        
        return {
            'success': True,
            'note_id': note_id,
            'processed_content': processed_content,
            'tags': tags,
            'capture_method': 'sms'
        }

    def _process_sms_content(self, message: str, sender: str) -> Dict[str, Any]:
        """Process SMS content with command parsing"""
        # Check for special SMS commands
        if message.startswith('#task '):
            return self._process_sms_task(message[6:])
        elif message.startswith('#reminder '):
            return self._process_sms_reminder(message[10:])
        elif message.startswith('#note '):
            return self._process_sms_note(message[6:])
        elif message.startswith('#idea '):
            return self._process_sms_idea(message[6:])
        elif message.startswith('#quote '):
            return self._process_sms_quote(message[7:])
        else:
            # Regular message
            return {
                'title': f"Text from {sender}",
                'content': f"# 💬 Text Message\n\n**From**: {sender}\n**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n**Message**:\n{message}"
            }

    def _process_sms_task(self, content: str) -> Dict[str, Any]:
        """Process task creation via SMS"""
        return {
            'title': f"Task: {content[:30]}{'...' if len(content) > 30 else ''}",
            'content': f"# ✅ {content}\n\n**Created via SMS**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n**Status**: Pending"
        }

    def _process_sms_reminder(self, content: str) -> Dict[str, Any]:
        """Process reminder creation via SMS"""
        return {
            'title': f"Reminder: {content[:30]}{'...' if len(content) > 30 else ''}",
            'content': f"# 🔔 {content}\n\n**Created via SMS**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n*Don't forget this!*"
        }

    def _process_sms_note(self, content: str) -> Dict[str, Any]:
        """Process note creation via SMS"""
        return {
            'title': f"Note: {content[:30]}{'...' if len(content) > 30 else ''}",
            'content': f"# 📝 Quick Note\n\n{content}\n\n**Captured via SMS**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }

    def _process_sms_idea(self, content: str) -> Dict[str, Any]:
        """Process idea capture via SMS"""
        return {
            'title': f"Idea: {content[:30]}{'...' if len(content) > 30 else ''}",
            'content': f"# 💡 {content}\n\n**Captured**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n*Expand on this idea later...*"
        }

    def _process_sms_quote(self, content: str) -> Dict[str, Any]:
        """Process quote capture via SMS"""
        return {
            'title': f"Quote: {content[:30]}{'...' if len(content) > 30 else ''}",
            'content': f"# 💭 Quote\n\n> {content}\n\n**Saved**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }

    # === Voice Processing ===
    
    def process_voice_capture(self, user_id: int, voice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process voice notes with transcription"""
        audio_file = voice_data.get('audio_file')
        transcription = voice_data.get('transcription', '')
        duration = voice_data.get('duration', 0)
        source = voice_data.get('source', 'voice_recorder')
        
        # If no transcription provided, we'd transcribe here
        if not transcription and audio_file:
            transcription = self._transcribe_audio(audio_file)
        
        # Process the transcription
        processed_content = self._process_voice_content(transcription, duration, source)
        
        # Generate tags
        tags = self._generate_voice_tags(transcription, source)
        
        # Save note
        note_id = self._save_mobile_note(
            user_id=user_id,
            content=processed_content['content'],
            title=processed_content['title'],
            tags=tags,
            note_type='voice',
            metadata={
                'capture_method': 'voice',
                'duration': duration,
                'source': source,
                'has_audio_file': audio_file is not None,
                'transcription_confidence': voice_data.get('confidence', 0.0),
                'timestamp': datetime.utcnow().isoformat()
            }
        )
        
        return {
            'success': True,
            'note_id': note_id,
            'processed_content': processed_content,
            'tags': tags,
            'transcription': transcription,
            'capture_method': 'voice'
        }

    def _transcribe_audio(self, audio_file: str) -> str:
        """Transcribe audio file using Whisper.cpp"""
        try:
            from audio_utils import transcribe_audio
            from pathlib import Path
            
            audio_path = Path(audio_file)
            if not audio_path.exists():
                return "Audio file not found"
            
            # Use the existing Whisper.cpp integration
            transcription = transcribe_audio(audio_path)
            return transcription if transcription else "Transcription failed"
            
        except Exception as e:
            print(f"Transcription error: {e}")
            return f"Transcription error: {str(e)}"

    def _process_voice_content(self, transcription: str, duration: int, source: str) -> Dict[str, Any]:
        """Process transcribed voice content"""
        formatted_content = "# 🎤 Voice Note\n\n"
        formatted_content += f"**Duration**: {duration} seconds\n"
        formatted_content += f"**Source**: {source}\n"
        formatted_content += f"**Recorded**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        formatted_content += "---\n\n"
        formatted_content += "**Transcription**:\n\n"
        formatted_content += transcription
        
        return {
            'title': f"Voice: {transcription[:40]}{'...' if len(transcription) > 40 else ''}",
            'content': formatted_content
        }

    # === Utility Methods ===
    
    def _generate_mobile_tags(self, content: str, capture_type: str, source_app: str, location: Dict) -> str:
        """Generate intelligent tags for mobile captures"""
        tags = ['mobile', capture_type, source_app.lower().replace(' ', '-')]
        
        # Add location-based tags
        if location:
            if location.get('name'):
                location_tag = location['name'].lower().replace(' ', '-')
                tags.append(location_tag)
            if location.get('type'):
                tags.append(location['type'])
        
        # Content-based tags
        content_tags = self._extract_content_tags(content)
        tags.extend(content_tags[:5])  # Limit to 5 additional tags
        
        return ','.join(tags)

    def _generate_email_tags(self, subject: str, sender: str, body: str) -> str:
        """Generate tags for email captures"""
        tags = ['email', 'forwarded']
        
        # Extract domain from sender
        if '@' in sender:
            domain = sender.split('@')[-1].lower()
            tags.append(domain.replace('.', '-'))
        
        # Subject-based tags
        subject_tags = self._extract_content_tags(subject)
        tags.extend(subject_tags[:3])
        
        # Body-based tags (limited)
        body_tags = self._extract_content_tags(body)
        tags.extend(body_tags[:2])
        
        return ','.join(tags)

    def _generate_sms_tags(self, message: str, sender: str) -> str:
        """Generate tags for SMS captures"""
        tags = ['sms', 'text-message']
        
        # Add sender as tag (cleaned)
        if sender:
            sender_tag = re.sub(r'[^\w\s-]', '', sender).lower().replace(' ', '-')
            tags.append(sender_tag)
        
        # Check for command tags
        if message.startswith('#'):
            command = message.split(' ')[0][1:]
            tags.append(command)
        
        # Content tags
        content_tags = self._extract_content_tags(message)
        tags.extend(content_tags[:3])
        
        return ','.join(tags)

    def _generate_voice_tags(self, transcription: str, source: str) -> str:
        """Generate tags for voice captures"""
        tags = ['voice', 'audio', source.lower().replace(' ', '-')]
        
        # Transcription-based tags
        if transcription:
            content_tags = self._extract_content_tags(transcription)
            tags.extend(content_tags[:5])
        
        return ','.join(tags)

    def _extract_content_tags(self, content: str) -> List[str]:
        """Extract meaningful tags from content"""
        if not content:
            return []
        
        # Simple keyword extraction
        words = re.findall(r'\b\w{4,}\b', content.lower())
        
        # Filter common words
        stopwords = {'that', 'this', 'with', 'have', 'will', 'from', 'they', 'been', 'were', 'said', 'what', 'your'}
        meaningful_words = [w for w in words if w not in stopwords]
        
        # Count frequency
        word_freq = {}
        for word in meaningful_words:
            word_freq[word] = word_freq.get(word, 0) + 1
        
        # Return top words
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:8]]

    def _save_mobile_note(self, user_id: int, content: str, title: str, tags: str, note_type: str, metadata: Dict) -> int:
        """Save mobile capture to database"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Insert note
        cursor.execute("""
            INSERT INTO notes (user_id, note, tags, type, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            content,
            tags,
            note_type,
            json.dumps(metadata),
            datetime.utcnow().isoformat()
        ))
        
        note_id = cursor.lastrowid
        
        # Update search index if exists
        try:
            cursor.execute("""
                INSERT INTO notes_fts (rowid, note, tags)
                VALUES (?, ?, ?)
            """, (note_id, content, tags))
        except sqlite3.OperationalError:
            # FTS table might not exist
            pass
        
        conn.commit()
        return note_id

    # === Admin and Utility Methods ===
    
    def get_capture_stats(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get mobile capture statistics"""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        # Get capture counts by method
        cursor.execute("""
            SELECT 
                JSON_EXTRACT(metadata, '$.capture_method') as method,
                COUNT(*) as count
            FROM notes 
            WHERE user_id = ? 
            AND created_at >= datetime('now', '-{} days')
            AND JSON_EXTRACT(metadata, '$.capture_method') IS NOT NULL
            GROUP BY JSON_EXTRACT(metadata, '$.capture_method')
        """.format(days), (user_id,))
        
        method_stats = dict(cursor.fetchall())
        
        # Get total mobile captures
        cursor.execute("""
            SELECT COUNT(*) 
            FROM notes 
            WHERE user_id = ? 
            AND created_at >= datetime('now', '-{} days')
            AND type IN ('mobile', 'email', 'sms', 'voice')
        """.format(days), (user_id,))
        
        total_mobile = cursor.fetchone()[0]
        
        return {
            'total_mobile_captures': total_mobile,
            'capture_methods': method_stats,
            'period_days': days
        }