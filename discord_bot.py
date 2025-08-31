# Discord Bot Integration
import discord
from discord.ext import commands
import aiohttp
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

SECOND_BRAIN_API = os.getenv('SECOND_BRAIN_API_URL', 'http://localhost:8082')
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

    async def save_to_second_brain(self, content: str, user_id: int, tags: str = ""):
        """Save content to Second Brain via API"""
        payload = {
            "note": content,
            "tags": tags,
            "type": "discord",
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
        """Save a note to Second Brain"""
        words = content.split()
        tags = [word[1:] for word in words if word.startswith('#')]
        note_content = ' '.join(word for word in words if not word.startswith('#'))
        
        success = await self.save_to_second_brain(note_content, ctx.author.id, ','.join(tags))
        
        if success:
            embed = discord.Embed(
                title="✅ Note Saved",
                description="Successfully saved to Second Brain",
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

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.add_cog(SecondBrainCog(bot))

if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_BOT_TOKEN'))
