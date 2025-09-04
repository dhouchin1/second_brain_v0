# discord_bot.py
# Discord Bot Integration with Slash Commands + FastAPI backend

import os
import sqlite3
from pathlib import Path
from datetime import datetime
import asyncio
import uuid
import tempfile

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Intents
intents = discord.Intents.default()
intents.message_content = True

# Global + Guild slash sync
TEST_GUILD_ID = os.getenv("DISCORD_GUILD_ID")

class SecondBrainBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Add the Cog
        await self.add_cog(SecondBrainCog(self))

        # Register slash commands
        if TEST_GUILD_ID:
            guild = discord.Object(id=int(TEST_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"🔗 Synced {len(synced)} guild commands to {guild.id}")
        else:
            synced = await self.tree.sync()
            print(f"🌍 Synced {len(synced)} global commands")

        print(f"✅ Slash commands ready for {self.user}")


bot = SecondBrainBot()

# API + secrets
SECOND_BRAIN_API = os.getenv("SECOND_BRAIN_API_URL", "http://localhost:8082")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "your-secret-token")


class SecondBrainCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        self.db_path = Path(__file__).parent / "notes.db"

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    # -------------------------
    # Helpers
    # -------------------------
    async def save_to_second_brain(self, content: str, user_id: int, tags: str = ""):
        payload = {
            "note": content,
            "tags": tags,
            "type": "discord",
            "discord_user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        headers = {"Authorization": f"Bearer {WEBHOOK_TOKEN}", "Content-Type": "application/json"}
        try:
            async with self.session.post(
                f"{SECOND_BRAIN_API}/webhook/discord", json=payload, headers=headers
            ) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Failed to save to Second Brain: {e}")
            return False

    def get_db_stats(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM notes")
            total_notes = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM notes WHERE created_at > datetime('now', '-1 day')"
            )
            recent_notes = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM processing_tasks")
            total_tasks = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM processing_tasks WHERE status = 'failed'")
            failed_tasks = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM processing_tasks WHERE status = 'pending'")
            pending_tasks = cursor.fetchone()[0]
            conn.close()
            return {
                "total_notes": total_notes,
                "recent_notes": recent_notes,
                "total_tasks": total_tasks,
                "failed_tasks": failed_tasks,
                "pending_tasks": pending_tasks,
            }
        except Exception as e:
            print(f"Database error: {e}")
            return None

    async def search_notes(self, query: str, limit: int = 5):
        try:
            async with self.session.get(
                f"{SECOND_BRAIN_API}/api/search?q={query}&limit={limit}",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
        except Exception as e:
            print(f"Search error: {e}")
            return None

    async def upload_file_to_backend(self, file: discord.Attachment, note: str, tags: str, user_id: int) -> dict:
        """Upload file to backend using Discord-specific webhook endpoint"""
        try:
            # Create a multipart form to upload the file directly
            data = aiohttp.FormData()
            
            # Add file content
            file_content = await file.read()
            data.add_field('file', file_content, filename=file.filename, content_type=file.content_type)
            
            # Add metadata
            data.add_field('note', note)
            data.add_field('tags', tags)
            data.add_field('discord_user_id', str(user_id))
            data.add_field('type', 'discord_upload')
            
            # Use Discord bot authentication
            headers = {
                "Authorization": f"Bearer {WEBHOOK_TOKEN}"
            }
            
            async with self.session.post(
                f"{SECOND_BRAIN_API}/webhook/discord/upload",
                data=data,
                headers=headers
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return {"success": False, "error": f"Upload failed ({resp.status}): {error_text}"}
                
                result = await resp.json()
                return {
                    "success": True,
                    "note_id": result.get("note_id"),
                    "extracted_text": result.get("extracted_text", ""),
                    "processing_type": result.get("processing_type", "unknown"),
                    "file_size": result.get("file_size"),
                    "transcription": result.get("transcription", "")
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def poll_processing_status(self, message: discord.WebhookMessage, note_id: int, filename: str):
        """Poll processing status and update the Discord message"""
        max_polls = 30  # 5 minutes max (10 second intervals)
        poll_count = 0
        
        while poll_count < max_polls:
            try:
                # Check processing status
                async with self.session.get(
                    f"{SECOND_BRAIN_API}/api/notes/{note_id}",
                    headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"}
                ) as resp:
                    if resp.status == 200:
                        note_data = await resp.json()
                        status = note_data.get("processing_status", "unknown")
                        
                        if status == "completed":
                            # Processing complete - update embed with final results
                            embed = discord.Embed(
                                title="✅ Processing Complete",
                                description=f"**File**: {filename}\n**Note ID**: {note_id}",
                                color=0x10B981,
                            )
                            
                            # Add transcription/extracted content if available
                            if note_data.get("transcription"):
                                transcription = note_data["transcription"][:300]
                                embed.add_field(
                                    name="🎵 Transcription",
                                    value=transcription + "..." if len(note_data["transcription"]) > 300 else transcription,
                                    inline=False
                                )
                            elif note_data.get("extracted_text"):
                                extracted = note_data["extracted_text"][:300]
                                embed.add_field(
                                    name="🔍 Extracted Text",
                                    value=extracted + "..." if len(note_data["extracted_text"]) > 300 else extracted,
                                    inline=False
                                )
                            
                            # Add file info
                            if note_data.get("file_size"):
                                embed.add_field(name="File Size", value=f"{note_data['file_size']:,} bytes", inline=True)
                            if note_data.get("file_type"):
                                embed.add_field(name="File Type", value=note_data["file_type"], inline=True)
                            
                            embed.add_field(
                                name="✅ Status", 
                                value="Ready for search and retrieval", 
                                inline=False
                            )
                            
                            await message.edit(embed=embed)
                            return
                        
                        elif status == "failed":
                            # Processing failed
                            error_msg = note_data.get("error_message", "Unknown error")
                            embed = discord.Embed(
                                title="❌ Processing Failed",
                                description=f"**File**: {filename}\n**Note ID**: {note_id}\n**Error**: {error_msg}",
                                color=0xEF4444,
                            )
                            embed.add_field(
                                name="🔄 Next Steps", 
                                value="You can retry processing with `/retry` command", 
                                inline=False
                            )
                            await message.edit(embed=embed)
                            return
                        
                        elif status in ["processing", "pending"]:
                            # Still processing - update status
                            current_embed = message.embeds[0] if message.embeds else None
                            if current_embed:
                                # Update the status field
                                for i, field in enumerate(current_embed.fields):
                                    if "Status" in field.name:
                                        current_embed.set_field_at(
                                            i, 
                                            name="Status", 
                                            value=f"⚙️ Processing... ({poll_count + 1}/{max_polls})", 
                                            inline=False
                                        )
                                        break
                                else:
                                    # Add status field if it doesn't exist
                                    current_embed.add_field(
                                        name="Status", 
                                        value=f"⚙️ Processing... ({poll_count + 1}/{max_polls})", 
                                        inline=False
                                    )
                                
                                await message.edit(embed=current_embed)
                        
                    await asyncio.sleep(10)  # Wait 10 seconds before next poll
                    poll_count += 1
                    
            except Exception as e:
                print(f"Error polling status for note {note_id}: {e}")
                break
        
        # Timeout reached
        embed = discord.Embed(
            title="⏰ Processing Timeout",
            description=f"**File**: {filename}\n**Note ID**: {note_id}",
            color=0xF59E0B,
        )
        embed.add_field(
            name="Status", 
            value="Processing is taking longer than expected. Check back later or use `/retry` if needed.", 
            inline=False
        )
        await message.edit(embed=embed)

    # -------------------------
    # Slash Commands
    # -------------------------
    @app_commands.command(name="save", description="Save a note to Second Brain")
    async def save_slash(self, interaction: discord.Interaction, content: str, tags: str = ""):
        await interaction.response.defer()
        success = await self.save_to_second_brain(content, interaction.user.id, tags)
        if success:
            embed = discord.Embed(
                title="✅ Note Saved",
                description="Successfully saved to Second Brain",
                color=0x4F46E5,
            )
            embed.add_field(
                name="Content",
                value=content[:100] + "..." if len(content) > 100 else content,
                inline=False,
            )
            if tags:
                embed.add_field(name="Tags", value=tags, inline=True)
        else:
            embed = discord.Embed(
                title="❌ Save Failed",
                description="Failed to save note to Second Brain",
                color=0xEF4444,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="search", description="Search your Second Brain notes")
    async def search_slash(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        results = await self.search_notes(query)
        if results and results.get("results"):
            embed = discord.Embed(
                title=f"🔍 Search Results for '{query}'", color=0x3B82F6
            )
            for i, result in enumerate(results["results"][:5], 1):
                title = result.get("title", "Untitled")[:50]
                content = result.get("content", "")[:100]
                embed.add_field(
                    name=f"{i}. {title}",
                    value=content + "..." if len(content) == 100 else content,
                    inline=False,
                )
        else:
            embed = discord.Embed(
                title="❌ No Results",
                description=f"No notes found for '{query}'",
                color=0x6B7280,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="upload", description="Upload and process files (audio, images, documents)")
    async def upload_slash(self, interaction: discord.Interaction, file: discord.Attachment, note: str = "", tags: str = ""):
        """Upload and process files through Second Brain"""
        await interaction.response.defer()
        
        # Validate file size (Discord has 25MB limit, backend might be different)
        max_size = 25 * 1024 * 1024  # 25MB Discord limit
        if file.size > max_size:
            embed = discord.Embed(
                title="❌ File Too Large",
                description=f"File size ({file.size:,} bytes) exceeds Discord's 25MB limit",
                color=0xEF4444,
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Validate file type
        supported_types = {
            # Audio types
            'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/wave', 'audio/x-pn-wav', 
            'audio/x-wav', 'audio/mp4', 'audio/m4a', 'audio/x-m4a', 'audio/aac',
            'audio/x-aac', 'audio/ogg', 'audio/webm', 'video/webm',
            # Image types  
            'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp',
            'image/tiff', 'image/webp',
            # Document types
            'application/pdf', 'text/plain'
        }
        
        # Get file extension for fallback type detection
        file_ext = Path(file.filename).suffix.lower() if file.filename else ""
        supported_extensions = {
            '.mp3', '.wav', '.m4a', '.ogg', '.webm', '.aac',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic',
            '.pdf', '.txt'
        }
        
        # Check if file type is supported
        is_supported = (
            file.content_type in supported_types or 
            file_ext in supported_extensions or
            file.content_type.startswith(('audio/', 'image/')) or
            'audio' in (file.content_type or '').lower() or
            'image' in (file.content_type or '').lower()
        )
        
        if not is_supported:
            embed = discord.Embed(
                title="❌ Unsupported File Type",
                description=f"File type `{file.content_type}` with extension `{file_ext}` is not supported.\n\n"
                           "**Supported types:**\n"
                           "• **Audio**: MP3, WAV, M4A, OGG, WebM, AAC\n"
                           "• **Images**: JPG, PNG, GIF, BMP, TIFF, WebP, HEIC\n"
                           "• **Documents**: PDF, TXT",
                color=0xEF4444,
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Create initial processing embed
        embed = discord.Embed(
            title="📤 Processing Upload",
            description=f"**File**: {file.filename}\n**Size**: {file.size:,} bytes\n**Type**: {file.content_type or 'Unknown'}",
            color=0x3B82F6,
        )
        embed.add_field(name="Status", value="🔄 Uploading to server...", inline=False)
        if note:
            embed.add_field(name="Note", value=note[:100] + "..." if len(note) > 100 else note, inline=False)
        if tags:
            embed.add_field(name="Tags", value=tags, inline=True)
        
        message = await interaction.followup.send(embed=embed)
        
        try:
            # Stream upload to backend
            result = await self.upload_file_to_backend(file, note, tags, interaction.user.id)
            
            if result['success']:
                # Update with success
                embed = discord.Embed(
                    title="✅ Upload Complete",
                    description=f"**File**: {file.filename}\n**Processed**: {result['note_id']}",
                    color=0x10B981,
                )
                
                # Add processing results
                if result.get('extracted_text'):
                    text_preview = result['extracted_text'][:200]
                    embed.add_field(
                        name="🔍 Extracted Text", 
                        value=text_preview + "..." if len(result['extracted_text']) > 200 else text_preview,
                        inline=False
                    )
                
                if result.get('processing_type'):
                    embed.add_field(name="Processing Type", value=result['processing_type'].title(), inline=True)
                
                if result.get('file_size'):
                    embed.add_field(name="File Size", value=f"{result['file_size']:,} bytes", inline=True)
                
                # Poll for async processing completion
                if result.get('processing_type') in ['audio', 'image', 'document']:
                    embed.add_field(name="Status", value="⚙️ Processing in background...", inline=False)
                    await message.edit(embed=embed)
                    
                    # Wait for processing to complete
                    await self.poll_processing_status(message, result['note_id'], file.filename)
                else:
                    await message.edit(embed=embed)
            else:
                # Update with error
                embed = discord.Embed(
                    title="❌ Upload Failed",
                    description=f"**File**: {file.filename}\n**Error**: {result['error']}",
                    color=0xEF4444,
                )
                await message.edit(embed=embed)
                
        except Exception as e:
            # Handle unexpected errors
            embed = discord.Embed(
                title="❌ Upload Error",
                description=f"**File**: {file.filename}\n**Error**: {str(e)}",
                color=0xEF4444,
            )
            await message.edit(embed=embed)

    @app_commands.command(name="status", description="Show Second Brain system status")
    async def status_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        stats = self.get_db_stats()
        if stats:
            embed = discord.Embed(title="🧠 Second Brain Status", color=0x10B981)
            embed.add_field(name="Total Notes", value=f"{stats['total_notes']:,}", inline=True)
            embed.add_field(name="Recent Notes (24h)", value=f"{stats['recent_notes']:,}", inline=True)
            embed.add_field(name="Processing Tasks", value=f"{stats['total_tasks']:,}", inline=True)
            embed.add_field(name="Pending Tasks", value=f"{stats['pending_tasks']:,}", inline=True)
            embed.add_field(name="Failed Tasks", value=f"{stats['failed_tasks']:,}", inline=True)
            embed.add_field(name="API Endpoint", value=SECOND_BRAIN_API, inline=False)
        else:
            embed = discord.Embed(
                title="❌ Status Unavailable",
                description="Could not retrieve system status",
                color=0xEF4444,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="stats", description="Show detailed statistics")
    async def stats_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with self.session.get(
                f"{SECOND_BRAIN_API}/api/stats",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                api_stats = await resp.json() if resp.status == 200 else None

            embed = discord.Embed(title="📊 Second Brain Statistics", color=0x8B5CF6)
            if api_stats:
                embed.add_field(
                    name="📝 Content Stats",
                    value=f"Notes: {api_stats.get('total_notes', 0)}\n"
                          f"Tags: {api_stats.get('total_tags', 0)}\n"
                          f"Files: {api_stats.get('total_files', 0)}",
                    inline=True,
                )
                embed.add_field(
                    name="🔍 Search Stats",
                    value=f"Searches: {api_stats.get('total_searches', 0)}\n"
                          f"Avg Response: {api_stats.get('avg_response_time', 0)}ms",
                    inline=True,
                )

            db_stats = self.get_db_stats()
            if db_stats:
                embed.add_field(
                    name="⚙️ Processing Stats",
                    value=f"Total Tasks: {db_stats['total_tasks']}\n"
                          f"Pending: {db_stats['pending_tasks']}\n"
                          f"Failed: {db_stats['failed_tasks']}",
                    inline=True,
                )
            embed.timestamp = datetime.utcnow()
        except Exception as e:
            embed = discord.Embed(
                title="❌ Stats Error",
                description=f"Could not retrieve statistics: {str(e)}",
                color=0xEF4444,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="restart", description="[ADMIN] Restart processing tasks")
    async def restart_slash(self, interaction: discord.Interaction, task_type: str = "failed"):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.session.post(
                f"{SECOND_BRAIN_API}/api/admin/restart-tasks",
                json={"task_type": task_type},
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    embed = discord.Embed(
                        title="🔄 Tasks Restarted",
                        description=f"Restarted {result.get('restarted', 0)} {task_type} tasks",
                        color=0x10B981,
                    )
                else:
                    embed = discord.Embed(
                        title="❌ Restart Failed",
                        description=f"Failed to restart tasks: {resp.status}",
                        color=0xEF4444,
                    )
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="cleanup", description="[ADMIN] Clean up old data")
    async def cleanup_slash(self, interaction: discord.Interaction, days: int = 30):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.session.post(
                f"{SECOND_BRAIN_API}/api/admin/cleanup",
                json={"days": days},
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    embed = discord.Embed(title="🧹 Cleanup Complete", color=0x10B981)
                    embed.add_field(name="Removed", value=f"{result.get('removed', 0)} items")
                    embed.add_field(name="Freed Space", value=f"{result.get('space_freed', 0)} MB")
                else:
                    embed = discord.Embed(
                        title="❌ Cleanup Failed", description=f"{resp.status}", color=0xEF4444
                    )
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="recent", description="Show recent notes")
    async def recent_slash(self, interaction: discord.Interaction, limit: int = 5):
        await interaction.response.defer()
        try:
            async with self.session.get(
                f"{SECOND_BRAIN_API}/api/notes/recent?limit={min(limit, 10)}",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    notes = await resp.json()
                    embed = discord.Embed(title=f"📝 {len(notes)} Recent Notes", color=0x6366F1)
                    for note in notes:
                        title = note.get("title", "Untitled")[:50]
                        content = note.get("content", "")[:100]
                        created = note.get("created_at", "")[:10]
                        embed.add_field(
                            name=f"📌 {title}",
                            value=f"{content}...\n*Created: {created}*",
                            inline=False,
                        )
                else:
                    embed = discord.Embed(title="❌ Error", description="Fetch failed", color=0xEF4444)
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="tags", description="List all available tags")
    async def tags_slash(self, interaction: discord.Interaction, limit: int = 20):
        await interaction.response.defer()
        try:
            async with self.session.get(
                f"{SECOND_BRAIN_API}/api/tags?limit={min(limit, 50)}",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    tags = await resp.json()
                    if tags:
                        embed = discord.Embed(title=f"🏷️ Popular Tags", color=0x10B981)
                        tag_list = []
                        for tag in tags[:limit]:
                            name = tag.get("tag", "").strip()
                            count = tag.get("count", 0)
                            if name:
                                tag_list.append(f"**{name}** ({count})")
                        
                        if tag_list:
                            # Split into chunks to fit Discord's field limit
                            chunk_size = 10
                            for i in range(0, len(tag_list), chunk_size):
                                chunk = tag_list[i:i + chunk_size]
                                field_name = f"Tags {i//chunk_size + 1}" if len(tag_list) > chunk_size else "Tags"
                                embed.add_field(
                                    name=field_name, 
                                    value="\n".join(chunk), 
                                    inline=True
                                )
                        else:
                            embed.description = "No tags found"
                    else:
                        embed = discord.Embed(
                            title="📝 No Tags", 
                            description="No tags found in your Second Brain", 
                            color=0x6B7280
                        )
                else:
                    embed = discord.Embed(title="❌ Error", description="Failed to fetch tags", color=0xEF4444)
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="sync", description="Trigger Obsidian vault sync")
    async def sync_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with self.session.post(
                f"{SECOND_BRAIN_API}/api/obsidian/sync",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    embed = discord.Embed(title="🔄 Obsidian Sync Complete", color=0x10B981)
                    embed.add_field(name="Synced", value=f"{result.get('synced', 0)} notes", inline=True)
                    embed.add_field(name="Updated", value=f"{result.get('updated', 0)} files", inline=True)
                else:
                    embed = discord.Embed(
                        title="❌ Sync Failed", 
                        description=f"Status: {resp.status}", 
                        color=0xEF4444
                    )
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="queue", description="Show processing queue status")
    async def queue_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            async with self.session.get(
                f"{SECOND_BRAIN_API}/api/queue/status",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    queue_data = await resp.json()
                    embed = discord.Embed(title="⚙️ Processing Queue", color=0x3B82F6)
                    
                    # Audio queue info
                    audio_queue = queue_data.get("audio_queue", {})
                    embed.add_field(
                        name="🎵 Audio Queue", 
                        value=f"Active: {audio_queue.get('active', 0)}\nPending: {audio_queue.get('pending', 0)}\nCompleted: {audio_queue.get('completed', 0)}", 
                        inline=True
                    )
                    
                    # Processing tasks
                    tasks = queue_data.get("processing_tasks", {})
                    embed.add_field(
                        name="📋 Processing Tasks",
                        value=f"Running: {tasks.get('running', 0)}\nPending: {tasks.get('pending', 0)}\nFailed: {tasks.get('failed', 0)}",
                        inline=True
                    )
                    
                    # System load
                    system = queue_data.get("system", {})
                    if system:
                        embed.add_field(
                            name="💾 System",
                            value=f"CPU: {system.get('cpu_percent', 0):.1f}%\nMemory: {system.get('memory_percent', 0):.1f}%",
                            inline=True
                        )
                    
                    embed.timestamp = datetime.utcnow()
                else:
                    embed = discord.Embed(title="❌ Error", description="Failed to get queue status", color=0xEF4444)
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="retry", description="Retry failed processing for a note")
    async def retry_slash(self, interaction: discord.Interaction, note_id: int):
        await interaction.response.defer()
        try:
            async with self.session.post(
                f"{SECOND_BRAIN_API}/api/notes/{note_id}/retry",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    embed = discord.Embed(
                        title="🔄 Processing Requeued", 
                        description=f"Note {note_id} has been queued for reprocessing", 
                        color=0x10B981
                    )
                elif resp.status == 404:
                    embed = discord.Embed(
                        title="❌ Note Not Found", 
                        description=f"Note {note_id} doesn't exist", 
                        color=0xEF4444
                    )
                else:
                    embed = discord.Embed(
                        title="❌ Retry Failed", 
                        description=f"Status: {resp.status}", 
                        color=0xEF4444
                    )
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="export", description="Export a note to different formats")
    async def export_slash(self, interaction: discord.Interaction, note_id: int, format: str = "markdown"):
        await interaction.response.defer()
        try:
            async with self.session.get(
                f"{SECOND_BRAIN_API}/api/notes/{note_id}/export?format={format}",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    content = await resp.text()
                    # Discord has a 2000 character limit, so we need to truncate or use a file
                    if len(content) > 1900:
                        # Create a temporary file and upload it
                        embed = discord.Embed(
                            title="📄 Note Export", 
                            description=f"Note {note_id} exported successfully (content too long for message)", 
                            color=0x10B981
                        )
                        # For now, just show a truncated version
                        embed.add_field(
                            name=f"Preview ({format})",
                            value=f"```{content[:1800]}...\n[truncated]```",
                            inline=False
                        )
                    else:
                        embed = discord.Embed(
                            title="📄 Note Export", 
                            description=f"Note {note_id} exported successfully", 
                            color=0x10B981
                        )
                        embed.add_field(
                            name=f"Content ({format})",
                            value=f"```{content}```",
                            inline=False
                        )
                elif resp.status == 404:
                    embed = discord.Embed(
                        title="❌ Note Not Found", 
                        description=f"Note {note_id} doesn't exist", 
                        color=0xEF4444
                    )
                else:
                    embed = discord.Embed(
                        title="❌ Export Failed", 
                        description=f"Status: {resp.status}", 
                        color=0xEF4444
                    )
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="duplicate", description="Duplicate an existing note")
    async def duplicate_slash(self, interaction: discord.Interaction, note_id: int, new_title: str = None):
        await interaction.response.defer()
        try:
            payload = {}
            if new_title:
                payload["new_title"] = new_title
                
            async with self.session.post(
                f"{SECOND_BRAIN_API}/api/notes/{note_id}/duplicate",
                json=payload,
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    embed = discord.Embed(
                        title="📋 Note Duplicated", 
                        description=f"Original note {note_id} duplicated successfully", 
                        color=0x10B981
                    )
                    embed.add_field(name="New Note ID", value=result.get("new_note_id"), inline=True)
                    embed.add_field(name="New Title", value=result.get("title", "Untitled"), inline=True)
                elif resp.status == 404:
                    embed = discord.Embed(
                        title="❌ Note Not Found", 
                        description=f"Note {note_id} doesn't exist", 
                        color=0xEF4444
                    )
                else:
                    embed = discord.Embed(
                        title="❌ Duplicate Failed", 
                        description=f"Status: {resp.status}", 
                        color=0xEF4444
                    )
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="activity", description="Show recent system activity")
    async def activity_slash(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer()
        try:
            async with self.session.get(
                f"{SECOND_BRAIN_API}/api/captures/recent?limit={min(limit, 20)}",
                headers={"Authorization": f"Bearer {WEBHOOK_TOKEN}"},
            ) as resp:
                if resp.status == 200:
                    activities = await resp.json()
                    if activities:
                        embed = discord.Embed(title="📊 Recent Activity", color=0x8B5CF6)
                        for activity in activities:
                            title = activity.get("title", "Untitled")[:40]
                            activity_type = activity.get("type", "unknown")
                            timestamp = activity.get("created_at", "")[:16].replace("T", " ")
                            status = activity.get("status", "unknown")
                            
                            status_emoji = {
                                "completed": "✅",
                                "processing": "⚙️", 
                                "pending": "⏳",
                                "failed": "❌"
                            }.get(status, "❓")
                            
                            embed.add_field(
                                name=f"{status_emoji} {title}",
                                value=f"Type: {activity_type}\nTime: {timestamp}\nStatus: {status}",
                                inline=True
                            )
                    else:
                        embed = discord.Embed(
                            title="📊 No Activity", 
                            description="No recent activity found", 
                            color=0x6B7280
                        )
                else:
                    embed = discord.Embed(title="❌ Error", description="Failed to get activity", color=0xEF4444)
        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e), color=0xEF4444)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="help", description="Show available commands")
    async def help_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Second Brain Bot Commands",
            description="Control your Second Brain from Discord",
            color=0x5865F2,
        )
        embed.add_field(
            name="📝 Content Commands",
            value="`/save` - Save a note\n`/search` - Search notes\n`/recent` - Show recent notes\n`/tags` - List all tags\n`/upload` - Upload files (audio, images, documents)",
            inline=False
        )
        embed.add_field(
            name="🔧 Management Commands", 
            value="`/export` - Export a note\n`/duplicate` - Duplicate a note\n`/retry` - Retry failed processing\n`/sync` - Sync with Obsidian",
            inline=False
        )
        embed.add_field(
            name="📊 Status Commands",
            value="`/status` - System status\n`/stats` - Detailed statistics\n`/queue` - Processing queue\n`/activity` - Recent activity",
            inline=False
        )
        embed.add_field(
            name="🔧 Admin Commands",
            value="`/restart` - Restart tasks\n`/cleanup` - Clean old data\n`/help` - This help",
            inline=False
        )
        await interaction.response.send_message(embed=embed)

    # -------------------------
    # Legacy Commands
    # -------------------------
    @commands.command(name="save")
    async def save_note(self, ctx, *, content):
        words = content.split()
        tags = [word[1:] for word in words if word.startswith("#")]
        note_content = " ".join(word for word in words if not word.startswith("#"))
        success = await self.save_to_second_brain(note_content, ctx.author.id, ",".join(tags))
        if success:
            embed = discord.Embed(title="✅ Note Saved", color=0x4F46E5)
            embed.add_field(name="Content", value=note_content, inline=False)
        else:
            embed = discord.Embed(title="❌ Save Failed", color=0xEF4444)
        await ctx.reply(embed=embed)


# -------------------------
# Events & Error Handlers
# -------------------------
@bot.event
async def on_ready():
    print(f"🤖 {bot.user} connected! In {len(bot.guilds)} servers.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(
            title="❓ Command Not Found",
            description="Try `/help` to see available commands",
            color=0x6B7280,
        )
        await ctx.reply(embed=embed)
    else:
        print(f"Command error: {error}")


@bot.event
async def on_application_command_error(interaction, error):
    embed = discord.Embed(
        title="❌ Command Error", description=f"{str(error)[:100]}", color=0xEF4444
    )
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ DISCORD_BOT_TOKEN not found in .env")
        exit(1)
    print("🚀 Starting Second Brain Discord Bot...")
    print(f"🔗 API Endpoint: {SECOND_BRAIN_API}")
    bot.run(token)
