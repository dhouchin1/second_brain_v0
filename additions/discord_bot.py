# discord_bot.py
import discord
from discord.ext import commands
import aiohttp
import os
from datetime import datetime
import asyncio

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
SECOND_BRAIN_API = os.getenv('SECOND_BRAIN_API_URL', 'http://localhost:8084')
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN', 'your-secret-token')

class SecondBrainCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
    
    async def cog_load(self):
        self.session = aiohttp.ClientSession()
    
    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def save_to_second_brain(self, content: str, user_id: int, tags: str = "", note_type: str = "discord"):
        """Save content to Second Brain via API"""
        payload = {
            "note": content,
            "tags": tags,
            "type": note_type,
            "discord_user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        headers = {
            "Authorization": f"Bearer {WEBHOOK_TOKEN}",
            "Content-Type": "application/json"
        }
        
        try:
            async with self.session.post(
                f"{SECOND_BRAIN_API}/webhook/discord", 
                json=payload, 
                headers=headers
            ) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Failed to save to Second Brain: {e}")
            return False

    @commands.command(name='save')
    async def save_note(self, ctx, *, content):
        """Save a note to Second Brain
        Usage: !save This is my note #meeting #important
        """
        # Extract tags from content
        words = content.split()
        tags = [word[1:] for word in words if word.startswith('#')]
        note_content = ' '.join(word for word in words if not word.startswith('#'))
        
        success = await self.save_to_second_brain(
            note_content, 
            ctx.author.id, 
            ','.join(tags)
        )
        
        if success:
            embed = discord.Embed(
                title="✅ Note Saved",
                description=f"Successfully saved to Second Brain",
                color=0x4F46E5
            )
            embed.add_field(name="Content", value=note_content[:100] + "..." if len(note_content) > 100 else note_content, inline=False)
            if tags:
                embed.add_field(name="Tags", value=" ".join(f"#{tag}" for tag in tags), inline=True)
        else:
            embed = discord.Embed(
                title="❌ Save Failed",
                description="Failed to save note to Second Brain",
                color=0xEF4444
            )
        
        await ctx.reply(embed=embed)

    @commands.command(name='capture')
    async def capture_thread(self, ctx, messages: int = 10):
        """Capture recent messages from this channel as a meeting note
        Usage: !capture 20 (captures last 20 messages)
        """
        if messages > 50:
            await ctx.reply("❌ Cannot capture more than 50 messages at once")
            return
        
        # Get recent messages
        async for message in ctx.channel.history(limit=messages + 1):  # +1 to exclude the command itself
            if message.id == ctx.message.id:
                continue
            messages_content = []
            
        async for message in ctx.channel.history(limit=messages + 1):
            if message.id == ctx.message.id:
                continue
            
            timestamp = message.created_at.strftime("%H:%M")
            author = message.author.display_name
            content = message.content
            
            if content:  # Skip empty messages
                messages_content.append(f"[{timestamp}] {author}: {content}")
        
        if not messages_content:
            await ctx.reply("❌ No messages to capture")
            return
        
        # Reverse to get chronological order
        messages_content.reverse()
        
        thread_content = f"Discord Thread Capture - #{ctx.channel.name}\n"
        thread_content += f"Captured at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        thread_content += "\n".join(messages_content)
        
        success = await self.save_to_second_brain(
            thread_content,
            ctx.author.id,
            f"discord,thread,{ctx.channel.name}",
            "discord_thread"
        )
        
        if success:
            embed = discord.Embed(
                title="✅ Thread Captured",
                description=f"Captured {len(messages_content)} messages from #{ctx.channel.name}",
                color=0x4F46E5
            )
        else:
            embed = discord.Embed(
                title="❌ Capture Failed",
                description="Failed to save thread to Second Brain",
                color=0xEF4444
            )
        
        await ctx.reply(embed=embed)

    @commands.command(name='remind')
    async def create_reminder(self, ctx, *, reminder_text):
        """Create a reminder note
        Usage: !remind Follow up on project proposal tomorrow
        """
        reminder_content = f"REMINDER: {reminder_text}\nCreated by: {ctx.author.display_name}\nChannel: #{ctx.channel.name}"
        
        success = await self.save_to_second_brain(
            reminder_content,
            ctx.author.id,
            "reminder,discord",
            "reminder"
        )
        
        if success:
            embed = discord.Embed(
                title="⏰ Reminder Created",
                description=reminder_text,
                color=0x10B981
            )
        else:
            embed = discord.Embed(
                title="❌ Reminder Failed",
                description="Failed to create reminder",
                color=0xEF4444
            )
        
        await ctx.reply(embed=embed)

    @commands.command(name='brain')
    async def brain_stats(self, ctx):
        """Show Second Brain statistics"""
        # This would query the API for user stats
        embed = discord.Embed(
            title="🧠 Second Brain Stats",
            description="Your personal knowledge base",
            color=0x6366F1
        )
        embed.add_field(name="Total Notes", value="247", inline=True)
        embed.add_field(name="This Week", value="23", inline=True)
        embed.add_field(name="Discord Notes", value="45", inline=True)
        embed.add_field(name="🔗 Dashboard", value=f"[Open Second Brain]({SECOND_BRAIN_API})", inline=False)
        
        await ctx.reply(embed=embed)

# Event handlers
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.add_cog(SecondBrainCog(bot))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Auto-save messages with specific reactions
    if "💾" in [str(reaction.emoji) for reaction in message.reactions]:
        cog = bot.get_cog('SecondBrainCog')
        if cog:
            await cog.save_to_second_brain(
                f"[Auto-saved from Discord]\n{message.content}",
                message.author.id,
                "discord,auto-save"
            )
    
    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_BOT_TOKEN'))