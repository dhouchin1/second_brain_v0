#!/usr/bin/env python3
"""
Validate Discord Bot Token and Get Correct Client ID
"""

import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def validate_token():
    """Validate Discord bot token and get real client ID"""
    
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ No DISCORD_BOT_TOKEN found in .env file")
        return
    
    print("🔍 Validating Discord bot token...")
    print(f"Token: {token[:24]}...")
    
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Get bot user info
            async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as response:
                if response.status == 200:
                    bot_info = await response.json()
                    client_id = bot_info['id']
                    bot_name = bot_info['username']
                    
                    print("✅ Token is valid!")
                    print(f"🤖 Bot Name: {bot_name}")
                    print(f"🆔 Client ID: {client_id}")
                    
                    # Generate correct invite URL
                    permissions = 2147870784  # Same permissions as before
                    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions={permissions}&scope=bot%20applications.commands"
                    
                    print("\n🔗 CORRECT Invite URL:")
                    print(invite_url)
                    
                    return client_id
                    
                elif response.status == 401:
                    print("❌ Token is invalid or expired")
                    print("💡 Go to Discord Developer Portal and generate a new token")
                    print("   https://discord.com/developers/applications")
                    
                else:
                    print(f"❌ API Error: {response.status}")
                    error_text = await response.text()
                    print(f"   {error_text}")
    
    except Exception as e:
        print(f"❌ Error validating token: {e}")

if __name__ == "__main__":
    asyncio.run(validate_token())