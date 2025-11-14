# ──────────────────────────────────────────────────────────────────────────────
# File: services/enhanced_apple_shortcuts_service.py
# ──────────────────────────────────────────────────────────────────────────────
"""
Enhanced Apple Shortcuts Integration for Second Brain

Advanced shortcuts for iOS/macOS including voice memos, photo OCR, location-based notes,
quick capture workflows, and deep integration with iOS features.
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import base64
import hashlib

from config import settings
from services.embeddings import Embeddings
from services.advanced_capture_service import get_advanced_capture_service, CaptureOptions
from llm_utils import ollama_summarize, ollama_generate_title

logger = logging.getLogger(__name__)

class EnhancedAppleShortcutsService:
    """Enhanced Apple Shortcuts integration service."""
    
    def __init__(self, get_conn_func):
        """Initialize with database connection function."""
        self.get_conn = get_conn_func
        self.embedder = Embeddings()
        self.advanced_capture = None
    
    def _get_advanced_capture(self):
        """Lazy load advanced capture service."""
        if not self.advanced_capture:
            self.advanced_capture = get_advanced_capture_service(self.get_conn)
        return self.advanced_capture
    
    async def process_voice_memo(
        self, 
        audio_data: str = None,
        audio_url: str = None,
        transcription: str = None,
        location_data: Dict = None,
        context: Dict = None
    ) -> Dict[str, Any]:
        """
        Process voice memo from iOS Shortcuts.
        
        Args:
            audio_data: Base64 encoded audio data
            audio_url: URL to audio file (if hosted)
            transcription: Pre-transcribed text from iOS
            location_data: GPS location info
            context: Additional context (time, app, etc.)
        """
        try:
            # Use transcription if provided (iOS can do this locally)
            if not transcription and audio_data:
                # Would need audio transcription service here
                # For now, use placeholder
                transcription = "Voice memo captured (transcription not available)"
            
            if not transcription:
                return {"success": False, "error": "No transcription or audio data provided"}
            
            # Generate title
            title = ollama_generate_title(transcription) or "Voice Memo"
            
            # Process with AI
            tags = ["voice-memo", "audio", "ios-shortcut"]
            summary = ""
            actions = []
            
            try:
                ai_result = ollama_summarize(transcription)
                if ai_result.get("summary"):
                    summary = ai_result["summary"]
                if ai_result.get("tags"):
                    tags.extend(ai_result["tags"])
                if ai_result.get("actions"):
                    actions.extend(ai_result["actions"])
            except Exception as e:
                logger.warning(f"AI processing failed: {e}")
            
            # Add location context if available
            location_text = ""
            if location_data:
                lat = location_data.get("latitude")
                lng = location_data.get("longitude")
                address = location_data.get("address", "")
                
                if lat and lng:
                    location_text = f"\n**Location:** {address} ({lat:.4f}, {lng:.4f})"
                    tags.append("location")
            
            # Add context information
            context_text = ""
            if context:
                timestamp = context.get("timestamp")
                app_name = context.get("app_name")
                device = context.get("device")
                
                context_parts = []
                if timestamp:
                    context_parts.append(f"Recorded: {timestamp}")
                if app_name:
                    context_parts.append(f"App: {app_name}")
                if device:
                    context_parts.append(f"Device: {device}")
                
                if context_parts:
                    context_text = f"\n**Context:** {' | '.join(context_parts)}"
            
            # Format content
            content = transcription
            if summary:
                content = f"**Summary:** {summary}\n\n**Transcription:**\n{transcription}"
            
            content += location_text + context_text
            
            if actions:
                content += f"\n\n**Action Items:**\n" + "\n".join([f"- {action}" for action in actions])
            
            # Save to database
            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "voice_memo",
                    "source": "ios_shortcuts",
                    "has_audio": bool(audio_data or audio_url),
                    "transcription_method": "ios_builtin" if transcription else "server",
                    "location": location_data,
                    "context": context,
                    "action_items_count": len(actions)
                }
            )
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "summary": summary,
                "action_items": actions,
                "tags": tags,
                "message": "Voice memo processed successfully"
            }
            
        except Exception as e:
            logger.error(f"Voice memo processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_photo_ocr(
        self,
        image_data: str,
        location_data: Dict = None,
        context: Dict = None
    ) -> Dict[str, Any]:
        """
        Process photo with OCR from iOS Shortcuts.
        
        Args:
            image_data: Base64 encoded image
            location_data: GPS location info
            context: Additional context
        """
        try:
            options = CaptureOptions(
                enable_ocr=True,
                enable_ai_processing=True,
                custom_tags=["photo", "ocr", "ios-shortcut"]
            )
            
            # Add location tag if available
            if location_data:
                options.custom_tags.append("location")
            
            # Use advanced capture service for OCR
            advanced_capture = self._get_advanced_capture()
            result = await advanced_capture.capture_screenshot_with_ocr(image_data, options)
            
            if result.success:
                # Add location and context info
                additional_content = ""
                
                if location_data:
                    lat = location_data.get("latitude")
                    lng = location_data.get("longitude")
                    address = location_data.get("address", "")
                    
                    if lat and lng:
                        additional_content += f"\n**Location:** {address} ({lat:.4f}, {lng:.4f})"
                
                if context:
                    timestamp = context.get("timestamp")
                    if timestamp:
                        additional_content += f"\n**Captured:** {timestamp}"
                
                if additional_content:
                    # Update the content in database
                    conn = self.get_conn()
                    cursor = conn.cursor()
                    
                    cursor.execute(
                        "UPDATE notes SET body = ? WHERE id = ?",
                        (result.content + additional_content, result.note_id)
                    )
                    conn.commit()
                    conn.close()
                
                return {
                    "success": True,
                    "note_id": result.note_id,
                    "title": result.title,
                    "extracted_text": result.content,
                    "tags": result.tags,
                    "message": "Photo OCR processed successfully"
                }
            else:
                return {
                    "success": False,
                    "error": result.error
                }
                
        except Exception as e:
            logger.error(f"Photo OCR processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_quick_note(
        self,
        text: str,
        note_type: str = "thought",
        location_data: Dict = None,
        context: Dict = None,
        auto_tag: bool = True
    ) -> Dict[str, Any]:
        """
        Process quick note from iOS Shortcuts.
        
        Args:
            text: Note content
            note_type: Type of note (thought, task, idea, meeting, etc.)
            location_data: GPS location info
            context: Additional context
            auto_tag: Whether to auto-generate tags
        """
        try:
            # Generate title
            title = ollama_generate_title(text) or f"{note_type.title()} Note"
            
            # Base tags
            tags = [note_type, "ios-shortcut", "quick-note"]
            
            # Add location tag
            if location_data:
                tags.append("location")
            
            # Auto-generate tags if enabled
            if auto_tag:
                try:
                    ai_result = ollama_summarize(text)
                    if ai_result.get("tags"):
                        tags.extend(ai_result["tags"][:5])  # Limit to 5 AI tags
                except Exception as e:
                    logger.warning(f"Auto-tagging failed: {e}")
            
            # Add location and context
            content = text
            
            if location_data:
                lat = location_data.get("latitude")
                lng = location_data.get("longitude")
                address = location_data.get("address", "")
                
                if lat and lng:
                    content += f"\n\n**Location:** {address} ({lat:.4f}, {lng:.4f})"
            
            if context:
                timestamp = context.get("timestamp")
                app_name = context.get("source_app")
                
                context_parts = []
                if timestamp:
                    context_parts.append(f"Created: {timestamp}")
                if app_name:
                    context_parts.append(f"From: {app_name}")
                
                if context_parts:
                    content += f"\n**Context:** {' | '.join(context_parts)}"
            
            # Save note
            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": f"quick_{note_type}",
                    "source": "ios_shortcuts",
                    "location": location_data,
                    "context": context,
                    "auto_tagged": auto_tag
                }
            )
            
            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "tags": tags,
                "message": f"{note_type.title()} note saved successfully"
            }
            
        except Exception as e:
            logger.error(f"Quick note processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_web_clip(
        self,
        url: str,
        selected_text: str = None,
        page_title: str = None,
        context: Dict = None
    ) -> Dict[str, Any]:
        """
        Process web clip from iOS Safari Share Sheet.
        
        Args:
            url: Web page URL
            selected_text: Selected text from page
            page_title: Page title
            context: Additional context
        """
        try:
            # Use web ingestion service
            from services.web_ingestion_service import WebIngestionService
            web_service = WebIngestionService()
            
            # If there's selected text, prioritize that
            if selected_text:
                title = page_title or ollama_generate_title(selected_text) or "Web Clip"
                
                content = f"**Source:** {url}\n\n"
                if page_title and page_title != title:
                    content += f"**Page:** {page_title}\n\n"
                content += f"**Selected Text:**\n{selected_text}"
                
                # Add context
                if context:
                    timestamp = context.get("timestamp")
                    if timestamp:
                        content += f"\n\n**Clipped:** {timestamp}"
                
                tags = ["web-clip", "ios-shortcut", "selected-text"]
                
                # Auto-generate tags from content
                try:
                    ai_result = ollama_summarize(selected_text)
                    if ai_result.get("tags"):
                        tags.extend(ai_result["tags"][:3])
                except Exception as e:
                    logger.warning(f"Auto-tagging failed: {e}")
                
                note_id = await self._save_note(
                    title=title,
                    content=content,
                    tags=tags,
                    metadata={
                        "content_type": "web_clip_selection",
                        "source": "ios_shortcuts",
                        "source_url": url,
                        "page_title": page_title,
                        "context": context,
                        "has_selection": True
                    }
                )
                
                return {
                    "success": True,
                    "note_id": note_id,
                    "title": title,
                    "content_type": "selection",
                    "message": "Web selection clipped successfully"
                }
            
            else:
                # Process full page
                web_result = await web_service.extract_and_process_url(url)
                
                if web_result:
                    # Add iOS context
                    additional_content = ""
                    if context:
                        timestamp = context.get("timestamp")
                        if timestamp:
                            additional_content = f"\n\n**Clipped via iOS:** {timestamp}"
                    
                    tags = ["web-clip", "ios-shortcut", "full-page"]
                    
                    note_id = await self._save_note(
                        title=web_result.title,
                        content=web_result.content + additional_content,
                        tags=tags,
                        metadata={
                            "content_type": "web_clip_full",
                            "source": "ios_shortcuts",
                            "source_url": url,
                            "context": context,
                            "has_selection": False
                        }
                    )
                    
                    return {
                        "success": True,
                        "note_id": note_id,
                        "title": web_result.title,
                        "content_type": "full_page",
                        "message": "Web page clipped successfully"
                    }
                else:
                    return {"success": False, "error": "Failed to extract web content"}
            
        except Exception as e:
            logger.error(f"Web clip processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_reading_list(
        self,
        url: str,
        title: str = None,
        preview_text: str = None,
        added_date: str = None,
        context: Dict = None
    ) -> Dict[str, Any]:
        """
        Process reading list article from Safari.

        Args:
            url: Article URL
            title: Article title
            preview_text: Preview/excerpt text
            added_date: When added to reading list
            context: Additional context
        """
        try:
            # Use web ingestion for full article
            from services.web_ingestion_service import WebIngestionService
            web_service = WebIngestionService()

            web_result = await web_service.extract_and_process_url(url)

            if web_result:
                # Use extracted title or provided title
                final_title = web_result.title or title or "Reading List Article"

                # Build content
                content = f"**Source:** {url}\n"
                if added_date:
                    content += f"**Added to Reading List:** {added_date}\n"
                content += f"\n{web_result.content}"

                if preview_text and preview_text not in web_result.content[:200]:
                    content = f"**Preview:** {preview_text}\n\n" + content

                tags = ["reading-list", "article", "ios-shortcut", "to-read"]

                # Auto-generate tags
                try:
                    ai_result = ollama_summarize(web_result.content[:1000])
                    if ai_result.get("tags"):
                        tags.extend(ai_result["tags"][:3])
                except Exception as e:
                    logger.warning(f"Auto-tagging failed: {e}")

                note_id = await self._save_note(
                    title=final_title,
                    content=content,
                    tags=tags,
                    metadata={
                        "content_type": "reading_list",
                        "source": "ios_shortcuts",
                        "source_url": url,
                        "added_date": added_date,
                        "context": context
                    }
                )

                return {
                    "success": True,
                    "note_id": note_id,
                    "title": final_title,
                    "message": "Reading list article saved"
                }
            else:
                return {"success": False, "error": "Failed to extract article content"}

        except Exception as e:
            logger.error(f"Reading list processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_contact_note(
        self,
        contact_name: str,
        contact_info: Dict = None,
        note_text: str = "",
        meeting_context: Dict = None,
        location_data: Dict = None
    ) -> Dict[str, Any]:
        """
        Create note about a contact/person.

        Args:
            contact_name: Person's name
            contact_info: Phone, email, company, etc.
            note_text: Note content about the person
            meeting_context: Meeting details if applicable
            location_data: Location of meeting/interaction
        """
        try:
            title = f"Note: {contact_name}"

            # Build structured content
            content = f"# {contact_name}\n\n"

            if contact_info:
                content += "## Contact Information\n"
                if contact_info.get("phone"):
                    content += f"- **Phone:** {contact_info['phone']}\n"
                if contact_info.get("email"):
                    content += f"- **Email:** {contact_info['email']}\n"
                if contact_info.get("company"):
                    content += f"- **Company:** {contact_info['company']}\n"
                if contact_info.get("title"):
                    content += f"- **Title:** {contact_info['title']}\n"
                content += "\n"

            if meeting_context:
                content += "## Meeting Context\n"
                if meeting_context.get("date"):
                    content += f"- **Date:** {meeting_context['date']}\n"
                if meeting_context.get("topic"):
                    content += f"- **Topic:** {meeting_context['topic']}\n"
                content += "\n"

            if location_data:
                lat = location_data.get("latitude")
                lng = location_data.get("longitude")
                address = location_data.get("address", "")
                if lat and lng:
                    content += f"**Location:** {address} ({lat:.4f}, {lng:.4f})\n\n"

            content += "## Notes\n"
            content += note_text if note_text else "_No notes yet_"

            tags = ["contact", "person", "ios-shortcut", contact_name.lower().replace(" ", "-")]
            if meeting_context:
                tags.append("meeting")

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "contact_note",
                    "source": "ios_shortcuts",
                    "contact_name": contact_name,
                    "contact_info": contact_info,
                    "meeting_context": meeting_context,
                    "location": location_data
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "contact": contact_name,
                "message": f"Contact note for {contact_name} saved"
            }

        except Exception as e:
            logger.error(f"Contact note processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_media_note(
        self,
        media_type: str,
        title: str,
        creator: str = None,
        notes: str = "",
        rating: int = None,
        tags_custom: List[str] = None,
        metadata_extra: Dict = None
    ) -> Dict[str, Any]:
        """
        Create note about book, movie, podcast, etc.

        Args:
            media_type: book, movie, podcast, article, video, etc.
            title: Title of the media
            creator: Author, director, host, etc.
            notes: User's notes/thoughts
            rating: 1-5 star rating
            tags_custom: Custom tags
            metadata_extra: ISBN, URL, duration, etc.
        """
        try:
            note_title = f"{media_type.title()}: {title}"

            # Build structured content
            content = f"# {title}\n\n"
            content += f"**Type:** {media_type.title()}\n"

            if creator:
                creator_label = {
                    "book": "Author",
                    "movie": "Director",
                    "podcast": "Host",
                    "article": "Author",
                    "video": "Creator"
                }.get(media_type.lower(), "Creator")
                content += f"**{creator_label}:** {creator}\n"

            if rating:
                content += f"**Rating:** {'⭐' * rating} ({rating}/5)\n"

            if metadata_extra:
                if metadata_extra.get("year"):
                    content += f"**Year:** {metadata_extra['year']}\n"
                if metadata_extra.get("genre"):
                    content += f"**Genre:** {metadata_extra['genre']}\n"
                if metadata_extra.get("isbn"):
                    content += f"**ISBN:** {metadata_extra['isbn']}\n"
                if metadata_extra.get("url"):
                    content += f"**URL:** {metadata_extra['url']}\n"

            content += f"\n## My Notes\n{notes if notes else '_No notes yet_'}\n"

            # Generate tags
            base_tags = [media_type.lower(), "media", "ios-shortcut"]
            if tags_custom:
                base_tags.extend(tags_custom)
            if rating and rating >= 4:
                base_tags.append("highly-rated")

            note_id = await self._save_note(
                title=note_title,
                content=content,
                tags=base_tags,
                metadata={
                    "content_type": f"media_{media_type}",
                    "source": "ios_shortcuts",
                    "media_type": media_type,
                    "media_title": title,
                    "creator": creator,
                    "rating": rating,
                    **({} if not metadata_extra else metadata_extra)
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": note_title,
                "media_type": media_type,
                "message": f"{media_type.title()} note saved"
            }

        except Exception as e:
            logger.error(f"Media note processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_recipe(
        self,
        recipe_name: str,
        ingredients: List[str],
        instructions: List[str],
        prep_time: str = None,
        cook_time: str = None,
        servings: int = None,
        source_url: str = None,
        tags_custom: List[str] = None,
        image_data: str = None
    ) -> Dict[str, Any]:
        """
        Save recipe with structured data.

        Args:
            recipe_name: Recipe title
            ingredients: List of ingredients
            instructions: Step-by-step instructions
            prep_time: Preparation time
            cook_time: Cooking time
            servings: Number of servings
            source_url: Source URL if from web
            tags_custom: Custom tags
            image_data: Base64 image of recipe
        """
        try:
            title = f"Recipe: {recipe_name}"

            # Build structured content
            content = f"# {recipe_name}\n\n"

            # Metadata section
            metadata_parts = []
            if prep_time:
                metadata_parts.append(f"⏱️ Prep: {prep_time}")
            if cook_time:
                metadata_parts.append(f"🍳 Cook: {cook_time}")
            if servings:
                metadata_parts.append(f"🍽️ Servings: {servings}")

            if metadata_parts:
                content += " | ".join(metadata_parts) + "\n\n"

            if source_url:
                content += f"**Source:** {source_url}\n\n"

            # Ingredients
            content += "## Ingredients\n\n"
            for ingredient in ingredients:
                content += f"- {ingredient}\n"
            content += "\n"

            # Instructions
            content += "## Instructions\n\n"
            for i, instruction in enumerate(instructions, 1):
                content += f"{i}. {instruction}\n"
            content += "\n"

            # Tags
            base_tags = ["recipe", "cooking", "food", "ios-shortcut"]
            if tags_custom:
                base_tags.extend(tags_custom)

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=base_tags,
                metadata={
                    "content_type": "recipe",
                    "source": "ios_shortcuts",
                    "recipe_name": recipe_name,
                    "prep_time": prep_time,
                    "cook_time": cook_time,
                    "servings": servings,
                    "source_url": source_url,
                    "has_image": bool(image_data),
                    "ingredient_count": len(ingredients),
                    "step_count": len(instructions)
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "ingredients_count": len(ingredients),
                "steps_count": len(instructions),
                "message": "Recipe saved successfully"
            }

        except Exception as e:
            logger.error(f"Recipe processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_dream_journal(
        self,
        dream_text: str,
        emotions: List[str] = None,
        themes: List[str] = None,
        lucid: bool = False,
        sleep_quality: int = None
    ) -> Dict[str, Any]:
        """
        Log dream journal entry.

        Args:
            dream_text: Dream description
            emotions: Emotions felt in dream
            themes: Dream themes/symbols
            lucid: Whether it was a lucid dream
            sleep_quality: 1-5 sleep quality rating
        """
        try:
            # Generate title from dream content
            title = ollama_generate_title(dream_text) or f"Dream Journal - {datetime.now().strftime('%Y-%m-%d')}"

            # Build content
            content = f"# {title}\n\n"
            content += f"**Date:** {datetime.now().strftime('%A, %B %d, %Y')}\n"

            if lucid:
                content += "**Type:** 🌟 Lucid Dream\n"

            if sleep_quality:
                content += f"**Sleep Quality:** {'⭐' * sleep_quality} ({sleep_quality}/5)\n"

            if emotions:
                content += f"**Emotions:** {', '.join(emotions)}\n"

            if themes:
                content += f"**Themes:** {', '.join(themes)}\n"

            content += f"\n## Dream Description\n\n{dream_text}\n"

            # Auto-analyze with AI
            try:
                ai_result = ollama_summarize(dream_text)
                if ai_result.get("summary"):
                    content += f"\n## AI Analysis\n\n{ai_result['summary']}\n"
            except Exception as e:
                logger.warning(f"AI analysis failed: {e}")

            tags = ["dream", "journal", "ios-shortcut", "morning"]
            if lucid:
                tags.append("lucid-dream")
            if emotions:
                tags.extend([e.lower() for e in emotions[:3]])

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "dream_journal",
                    "source": "ios_shortcuts",
                    "dream_date": datetime.now().date().isoformat(),
                    "lucid": lucid,
                    "sleep_quality": sleep_quality,
                    "emotions": emotions,
                    "themes": themes
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "lucid": lucid,
                "message": "Dream journal entry saved"
            }

        except Exception as e:
            logger.error(f"Dream journal processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_quote(
        self,
        quote_text: str,
        author: str = None,
        source: str = None,
        category: str = None,
        reflection: str = None,
        context: Dict = None
    ) -> Dict[str, Any]:
        """
        Save inspirational quote with attribution.

        Args:
            quote_text: The quote
            author: Quote author
            source: Book, speech, etc.
            category: Quote category/theme
            reflection: User's reflection on the quote
            context: Additional context
        """
        try:
            # Generate title
            title_text = quote_text[:50] + "..." if len(quote_text) > 50 else quote_text
            title = f"Quote: {title_text}"
            if author:
                title = f"Quote by {author}"

            # Build content
            content = f"# Quote\n\n"
            content += f"> {quote_text}\n\n"

            if author:
                content += f"**— {author}"
                if source:
                    content += f", _{source}_"
                content += "**\n\n"
            elif source:
                content += f"**Source:** {source}\n\n"

            if category:
                content += f"**Category:** {category}\n\n"

            if reflection:
                content += f"## My Reflection\n\n{reflection}\n"

            # Tags
            tags = ["quote", "inspiration", "ios-shortcut"]
            if author:
                tags.append(author.lower().replace(" ", "-"))
            if category:
                tags.append(category.lower())

            # Auto-generate thematic tags
            try:
                ai_result = ollama_summarize(quote_text + (f"\n\nReflection: {reflection}" if reflection else ""))
                if ai_result.get("tags"):
                    tags.extend(ai_result["tags"][:3])
            except Exception as e:
                logger.warning(f"Auto-tagging failed: {e}")

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "quote",
                    "source": "ios_shortcuts",
                    "author": author,
                    "source_work": source,
                    "category": category,
                    "has_reflection": bool(reflection),
                    "context": context
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "author": author,
                "message": "Quote saved successfully"
            }

        except Exception as e:
            logger.error(f"Quote processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_code_snippet(
        self,
        code: str,
        language: str,
        description: str = None,
        tags_custom: List[str] = None,
        source_url: str = None
    ) -> Dict[str, Any]:
        """
        Save code snippet with syntax highlighting.

        Args:
            code: Code content
            language: Programming language
            description: What the code does
            tags_custom: Custom tags
            source_url: Source URL if from web
        """
        try:
            # Generate title
            if description:
                title = f"Code: {description[:50]}"
            else:
                title = f"{language.title()} Snippet"

            # Build content
            content = f"# {title}\n\n"

            if description:
                content += f"{description}\n\n"

            if source_url:
                content += f"**Source:** {source_url}\n\n"

            content += f"```{language}\n{code}\n```\n"

            # Tags
            tags = ["code", "snippet", language.lower(), "ios-shortcut", "development"]
            if tags_custom:
                tags.extend(tags_custom)

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "code_snippet",
                    "source": "ios_shortcuts",
                    "language": language,
                    "source_url": source_url,
                    "line_count": len(code.split('\n'))
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "language": language,
                "message": "Code snippet saved"
            }

        except Exception as e:
            logger.error(f"Code snippet processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_travel_journal(
        self,
        entry_text: str,
        location_data: Dict,
        photos: List[str] = None,
        activity_type: str = None,
        companions: List[str] = None,
        expenses: Dict = None
    ) -> Dict[str, Any]:
        """
        Create travel journal entry with rich location data.

        Args:
            entry_text: Journal entry text
            location_data: GPS and location details
            photos: Base64 encoded photos
            activity_type: Type of activity (sightseeing, food, etc.)
            companions: People you're traveling with
            expenses: Cost tracking
        """
        try:
            # Extract location info
            place_name = location_data.get("address", "Unknown Location")
            lat = location_data.get("latitude")
            lng = location_data.get("longitude")

            title = f"Travel: {place_name}"

            # Build content
            content = f"# {place_name}\n\n"
            content += f"**Date:** {datetime.now().strftime('%A, %B %d, %Y')}\n"

            if lat and lng:
                content += f"**Coordinates:** [{lat:.4f}, {lng:.4f}](https://maps.google.com/?q={lat},{lng})\n"

            if activity_type:
                content += f"**Activity:** {activity_type}\n"

            if companions:
                content += f"**With:** {', '.join(companions)}\n"

            if expenses:
                total = expenses.get("amount", 0)
                currency = expenses.get("currency", "USD")
                content += f"**Cost:** {total} {currency}\n"

            content += f"\n## Journal Entry\n\n{entry_text}\n"

            if photos:
                content += f"\n_📸 {len(photos)} photo(s) attached_\n"

            # Tags
            tags = ["travel", "journal", "location", "ios-shortcut"]
            if activity_type:
                tags.append(activity_type.lower())

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "travel_journal",
                    "source": "ios_shortcuts",
                    "location": location_data,
                    "activity_type": activity_type,
                    "companions": companions,
                    "expenses": expenses,
                    "photo_count": len(photos) if photos else 0
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "location": place_name,
                "message": "Travel journal entry saved"
            }

        except Exception as e:
            logger.error(f"Travel journal processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_habit_log(
        self,
        habit_name: str,
        completed: bool,
        notes: str = None,
        mood: str = None,
        difficulty: int = None
    ) -> Dict[str, Any]:
        """
        Log habit completion/tracking.

        Args:
            habit_name: Name of habit
            completed: Whether habit was completed
            notes: Additional notes
            mood: How you felt
            difficulty: 1-5 difficulty rating
        """
        try:
            status = "✅ Completed" if completed else "❌ Missed"
            title = f"Habit: {habit_name} - {status}"

            # Build content
            content = f"# {habit_name}\n\n"
            content += f"**Date:** {datetime.now().strftime('%A, %B %d, %Y')}\n"
            content += f"**Status:** {status}\n"

            if mood:
                content += f"**Mood:** {mood}\n"

            if difficulty:
                content += f"**Difficulty:** {'⭐' * difficulty} ({difficulty}/5)\n"

            if notes:
                content += f"\n## Notes\n\n{notes}\n"

            # Tags
            tags = ["habit", "tracking", "ios-shortcut", habit_name.lower().replace(" ", "-")]
            if completed:
                tags.append("completed")
            else:
                tags.append("missed")

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "habit_log",
                    "source": "ios_shortcuts",
                    "habit_name": habit_name,
                    "completed": completed,
                    "log_date": datetime.now().date().isoformat(),
                    "mood": mood,
                    "difficulty": difficulty
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "habit": habit_name,
                "completed": completed,
                "message": f"Habit '{habit_name}' logged"
            }

        except Exception as e:
            logger.error(f"Habit log processing failed: {e}")
            return {"success": False, "error": str(e)}

    async def process_file_upload(
        self,
        file_data: str,
        file_name: str,
        file_type: str,
        description: str = None,
        tags_custom: List[str] = None
    ) -> Dict[str, Any]:
        """
        Upload file from Files app.

        Args:
            file_data: Base64 encoded file
            file_name: Original file name
            file_type: MIME type
            description: File description
            tags_custom: Custom tags
        """
        try:
            title = f"File: {file_name}"

            # Build content
            content = f"# {file_name}\n\n"
            content += f"**Type:** {file_type}\n"
            content += f"**Uploaded:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

            if description:
                content += f"\n## Description\n\n{description}\n"

            # Determine file category
            category = "document"
            if file_type.startswith("image/"):
                category = "image"
            elif file_type.startswith("video/"):
                category = "video"
            elif file_type.startswith("audio/"):
                category = "audio"
            elif "pdf" in file_type:
                category = "pdf"

            tags = ["file", "upload", category, "ios-shortcut"]
            if tags_custom:
                tags.extend(tags_custom)

            # Get file size estimate
            file_size_kb = len(file_data) * 3 / 4 / 1024  # Approximate base64 to bytes

            note_id = await self._save_note(
                title=title,
                content=content,
                tags=tags,
                metadata={
                    "content_type": "file_upload",
                    "source": "ios_shortcuts",
                    "file_name": file_name,
                    "file_type": file_type,
                    "file_category": category,
                    "file_size_kb": round(file_size_kb, 2),
                    "has_file_data": True
                }
            )

            return {
                "success": True,
                "note_id": note_id,
                "title": title,
                "file_name": file_name,
                "file_type": file_type,
                "message": f"File '{file_name}' uploaded successfully"
            }

        except Exception as e:
            logger.error(f"File upload processing failed: {e}")
            return {"success": False, "error": str(e)}

    def get_shortcut_templates(self) -> List[Dict[str, Any]]:
        """Get pre-built iOS Shortcuts templates."""
        return [
            {
                "name": "Quick Voice Memo",
                "description": "Record and transcribe voice memos with location",
                "endpoint": "/api/shortcuts/voice-memo",
                "method": "POST",
                "parameters": {
                    "transcription": "Quick Note dictated text",
                    "location_data": {
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "address": "San Francisco, CA"
                    },
                    "context": {
                        "timestamp": "2024-12-15T10:30:00Z",
                        "device": "iPhone"
                    }
                },
                "shortcut_url": f"{settings.base_dir}/shortcuts/voice_memo.shortcut"
            },
            {
                "name": "Photo OCR Capture",
                "description": "Take photo and extract text with OCR",
                "endpoint": "/api/shortcuts/photo-ocr",
                "method": "POST",
                "parameters": {
                    "image_data": "base64_image_data_here",
                    "location_data": {
                        "latitude": 37.7749,
                        "longitude": -122.4194
                    }
                },
                "shortcut_url": f"{settings.base_dir}/shortcuts/photo_ocr.shortcut"
            },
            {
                "name": "Quick Thought Capture",
                "description": "Quickly capture thoughts and ideas",
                "endpoint": "/api/shortcuts/quick-note",
                "method": "POST",
                "parameters": {
                    "text": "Your thought or idea here",
                    "note_type": "thought",
                    "auto_tag": True
                },
                "shortcut_url": f"{settings.base_dir}/shortcuts/quick_thought.shortcut"
            },
            {
                "name": "Web Clip from Safari",
                "description": "Clip web content from Safari share sheet",
                "endpoint": "/api/shortcuts/web-clip",
                "method": "POST",
                "parameters": {
                    "url": "https://example.com",
                    "selected_text": "Selected text from page",
                    "page_title": "Page Title"
                },
                "shortcut_url": f"{settings.base_dir}/shortcuts/web_clip.shortcut"
            },
            {
                "name": "Meeting Notes Starter",
                "description": "Quick meeting notes with attendees and agenda",
                "endpoint": "/api/shortcuts/quick-note",
                "method": "POST",
                "parameters": {
                    "text": "Meeting with [attendees] about [topic]",
                    "note_type": "meeting",
                    "auto_tag": True
                },
                "shortcut_url": f"{settings.base_dir}/shortcuts/meeting_notes.shortcut"
            },
            {
                "name": "Reading List Saver",
                "description": "Save articles from Safari reading list",
                "endpoint": "/api/shortcuts/reading-list",
                "method": "POST"
            },
            {
                "name": "Contact Notes",
                "description": "Quick notes about people you meet",
                "endpoint": "/api/shortcuts/contact-note",
                "method": "POST"
            },
            {
                "name": "Book/Media Logger",
                "description": "Track books, movies, podcasts",
                "endpoint": "/api/shortcuts/media-note",
                "method": "POST"
            },
            {
                "name": "Recipe Saver",
                "description": "Save recipes with ingredients and steps",
                "endpoint": "/api/shortcuts/recipe",
                "method": "POST"
            },
            {
                "name": "Dream Journal",
                "description": "Morning dream logging",
                "endpoint": "/api/shortcuts/dream-journal",
                "method": "POST"
            },
            {
                "name": "Quote Capture",
                "description": "Save inspiring quotes with attribution",
                "endpoint": "/api/shortcuts/quote",
                "method": "POST"
            },
            {
                "name": "Code Snippet Saver",
                "description": "Save code snippets with syntax highlighting",
                "endpoint": "/api/shortcuts/code-snippet",
                "method": "POST"
            },
            {
                "name": "Travel Journal",
                "description": "Rich travel logging with location",
                "endpoint": "/api/shortcuts/travel-journal",
                "method": "POST"
            },
            {
                "name": "Habit Tracker",
                "description": "Log daily habit completions",
                "endpoint": "/api/shortcuts/habit-log",
                "method": "POST"
            },
            {
                "name": "File Uploader",
                "description": "Upload files from Files app",
                "endpoint": "/api/shortcuts/file-upload",
                "method": "POST"
            }
        ]
    
    async def _save_note(
        self,
        title: str,
        content: str,
        tags: List[str],
        metadata: Dict[str, Any]
    ) -> int:
        """Save note to database with embeddings."""
        conn = self.get_conn()
        cursor = conn.cursor()
        
        try:
            # Clean tags
            tags_str = ", ".join(set(tag.strip() for tag in tags if tag.strip()))
            
            # Insert note
            cursor.execute("""
                INSERT INTO notes (title, body, tags, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                title,
                content,
                tags_str,
                json.dumps(metadata),
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))
            
            note_id = cursor.lastrowid
            
            # Generate embeddings
            try:
                embedding_text = f"{title}\n\n{content}"
                embedding = self.embedder.embed(embedding_text)
                
                # Store in vector table if available
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='note_vecs'")
                    if cursor.fetchone():
                        cursor.execute(
                            "INSERT OR REPLACE INTO note_vecs(note_id, embedding) VALUES (?, ?)",
                            (note_id, json.dumps(embedding))
                        )
                except Exception as e:
                    logger.debug(f"Vector storage not available: {e}")
                    
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")
            
            conn.commit()
            return note_id
            
        finally:
            conn.close()


def get_enhanced_apple_shortcuts_service(get_conn_func):
    """Factory function to get enhanced Apple shortcuts service."""
    return EnhancedAppleShortcutsService(get_conn_func)