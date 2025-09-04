#!/usr/bin/env python3
"""
Generate Discord Bot Invite URL
"""

import os
from dotenv import load_dotenv

load_dotenv()

def get_bot_invite_url():
    """Generate bot invite URL"""
    
    # Get client ID from token (first part before first dot)
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ No DISCORD_BOT_TOKEN found in .env file")
        return
    
    try:
        # Extract client ID from token
        client_id = token.split('.')[0]
        
        # Bot permissions
        permissions = [
            "send_messages",           # 2048
            "use_slash_commands",      # 2147483648
            "embed_links",             # 16384  
            "read_message_history",    # 65536
            "manage_messages",         # 8192
            "add_reactions",           # 64
            "attach_files",            # 32768
            "use_external_emojis"      # 262144
        ]
        
        # Calculate permissions value
        permission_values = {
            "send_messages": 2048,
            "use_slash_commands": 2147483648,
            "embed_links": 16384,
            "read_message_history": 65536,
            "manage_messages": 8192,
            "add_reactions": 64,
            "attach_files": 32768,
            "use_external_emojis": 262144
        }
        
        total_permissions = sum(permission_values[perm] for perm in permissions)
        
        # Generate invite URL
        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions={total_permissions}&scope=bot%20applications.commands"
        
        print("🤖 Discord Bot Invite URL")
        print("=" * 50)
        print(f"Bot Client ID: {client_id}")
        print("\n📋 Copy this URL to invite your bot:")
        print(invite_url)
        print("\n🔗 Or click this link:")
        print(f"https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions={total_permissions}&scope=bot%20applications.commands")
        
        print(f"\n✅ Permissions included ({total_permissions}):")
        for perm in permissions:
            print(f"   - {perm.replace('_', ' ').title()}")
        
        print("\n📝 Steps:")
        print("1. Click the URL above")
        print("2. Select your Discord server")
        print("3. Click 'Authorize'")
        print("4. Your bot will join the server!")
        
    except Exception as e:
        print(f"❌ Error generating invite URL: {e}")
        print("💡 Make sure your DISCORD_BOT_TOKEN is correct")

if __name__ == "__main__":
    get_bot_invite_url()