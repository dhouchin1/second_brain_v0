#!/usr/bin/env python3
"""
Discord Bot Setup for Second Brain
"""

import os
from pathlib import Path

def setup_discord_bot():
    """Interactive setup for Discord bot"""
    print("🤖 Second Brain - Discord Bot Setup")
    print("=" * 50)
    
    print("\n📋 Discord Bot Setup Steps:")
    print("1. Go to https://discord.com/developers/applications")
    print("2. Create a 'New Application'")
    print("3. Go to 'Bot' section and create a bot")
    print("4. Copy the bot token (keep it secret!)")
    print("5. Go to 'OAuth2' > 'URL Generator'")
    print("6. Select 'bot' and 'applications.commands' scopes")
    print("7. Select these bot permissions:")
    print("   - Send Messages")
    print("   - Use Slash Commands") 
    print("   - Embed Links")
    print("   - Read Message History")
    print("8. Use the generated URL to invite your bot")
    
    print("\n" + "="*30)
    token = input("Enter your Discord Bot Token: ").strip()
    
    if not token:
        print("❌ No token provided")
        return
    
    # Update .env file
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        # Read existing .env
        lines = env_file.read_text().splitlines()
        
        # Remove existing Discord config
        filtered_lines = [
            line for line in lines 
            if not line.startswith('DISCORD_BOT_TOKEN')
        ]
        
        # Add new Discord config
        filtered_lines.append(f"DISCORD_BOT_TOKEN={token}")
        
        # Write back
        env_file.write_text('\n'.join(filtered_lines) + '\n')
        
        print("✅ Discord bot token saved to .env file!")
    else:
        # Create new .env
        env_file.write_text(f"DISCORD_BOT_TOKEN={token}\n")
        print("✅ Created .env file with Discord bot token!")
    
    print("\n🚀 To start your bot:")
    print("   python discord_bot.py")
    
    print("\n📚 Available Commands:")
    print("   /save <content> [tags] - Save a note")
    print("   /search <query> - Search notes") 
    print("   /status - Show system status")
    print("   /stats - Show detailed statistics")
    print("   /recent [limit] - Show recent notes")
    print("   /help - Show all commands")
    print("   /restart [task_type] - [ADMIN] Restart tasks")
    print("   /cleanup [days] - [ADMIN] Clean old data")
    
    print("\n🔐 Make sure your Second Brain server is running on:")
    print("   http://localhost:8082 (or update SECOND_BRAIN_API_URL)")

def show_discord_status():
    """Show current Discord bot status"""
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        with open(env_file) as f:
            content = f.read()
            if 'DISCORD_BOT_TOKEN' in content:
                print("✅ Discord bot token is configured")
                print("🚀 Run: python discord_bot.py")
            else:
                print("❌ Discord bot token not found in .env")
                print("🔧 Run: python setup_discord_bot.py")
    else:
        print("❌ No .env file found")
        print("🔧 Run: python setup_discord_bot.py")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        show_discord_status()
    else:
        setup_discord_bot()