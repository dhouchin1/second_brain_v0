#!/usr/bin/env python3
"""
Email Service Setup for Magic Link Authentication
"""

import os
from pathlib import Path

def setup_email_service():
    """Interactive setup for email service"""
    print("🧠 Second Brain - Email Service Setup")
    print("=" * 50)
    
    env_file = Path(__file__).parent / ".env"
    
    print("\n📧 Choose your email service:")
    print("1. Resend (recommended) - 3,000 emails/month free")
    print("2. SendGrid - 100 emails/day free")
    print("3. Mailgun - 1,000 emails/month for 3 months")
    print("4. SMTP - Use your own email server")
    print("5. Disable email (console only)")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    env_vars = []
    
    if choice == "1":  # Resend
        print("\n🎯 Resend Setup:")
        print("1. Go to https://resend.com/")
        print("2. Sign up for free account")
        print("3. Verify your domain or use resend.dev for testing")
        print("4. Get your API key from the dashboard")
        
        api_key = input("\nEnter your Resend API key: ").strip()
        from_email = input("Enter from email (e.g., noreply@yourdomain.com): ").strip()
        
        env_vars = [
            "EMAIL_ENABLED=true",
            "EMAIL_SERVICE=resend",
            f"EMAIL_API_KEY={api_key}",
            f"EMAIL_FROM={from_email}",
            "EMAIL_FROM_NAME=Second Brain"
        ]
        
    elif choice == "2":  # SendGrid
        print("\n📤 SendGrid Setup:")
        print("1. Go to https://sendgrid.com/")
        print("2. Sign up for free account")
        print("3. Create an API key in Settings > API Keys")
        print("4. Verify your sender identity")
        
        api_key = input("\nEnter your SendGrid API key: ").strip()
        from_email = input("Enter from email: ").strip()
        
        env_vars = [
            "EMAIL_ENABLED=true",
            "EMAIL_SERVICE=sendgrid", 
            f"EMAIL_API_KEY={api_key}",
            f"EMAIL_FROM={from_email}",
            "EMAIL_FROM_NAME=Second Brain"
        ]
        
    elif choice == "3":  # Mailgun
        print("\n📮 Mailgun Setup:")
        print("1. Go to https://mailgun.com/")
        print("2. Sign up for free account")
        print("3. Add and verify your domain")
        print("4. Get your API key from the dashboard")
        
        api_key = input("\nEnter your Mailgun API key: ").strip()
        from_email = input("Enter from email: ").strip()
        
        env_vars = [
            "EMAIL_ENABLED=true",
            "EMAIL_SERVICE=mailgun",
            f"EMAIL_API_KEY={api_key}",
            f"EMAIL_FROM={from_email}",
            "EMAIL_FROM_NAME=Second Brain"
        ]
        
    elif choice == "4":  # SMTP
        print("\n📨 SMTP Setup:")
        print("Use your existing email server (Gmail, Outlook, etc.)")
        
        host = input("SMTP Host (e.g., smtp.gmail.com): ").strip()
        port = input("SMTP Port (587): ").strip() or "587"
        username = input("SMTP Username: ").strip()
        password = input("SMTP Password: ").strip()
        from_email = input("From Email: ").strip()
        
        env_vars = [
            "EMAIL_ENABLED=true",
            "EMAIL_SERVICE=smtp",
            f"SMTP_HOST={host}",
            f"SMTP_PORT={port}",
            f"SMTP_USERNAME={username}",
            f"SMTP_PASSWORD={password}",
            f"EMAIL_FROM={from_email}",
            "EMAIL_FROM_NAME=Second Brain",
            "SMTP_USE_TLS=true"
        ]
        
    elif choice == "5":  # Disable
        env_vars = ["EMAIL_ENABLED=false"]
        print("\n📧 Email disabled - magic links will be printed to console")
        
    else:
        print("❌ Invalid choice")
        return
    
    # Update .env file
    if env_vars:
        print(f"\n💾 Writing configuration to {env_file}")
        
        # Read existing .env
        existing_lines = []
        if env_file.exists():
            existing_lines = env_file.read_text().splitlines()
        
        # Remove existing email config lines
        email_prefixes = ['EMAIL_', 'SMTP_', 'RESEND_', 'SENDGRID_', 'MAILGUN_']
        filtered_lines = [
            line for line in existing_lines 
            if not any(line.startswith(prefix) for prefix in email_prefixes)
        ]
        
        # Add new config
        filtered_lines.extend(env_vars)
        
        # Write back to .env
        env_file.write_text('\n'.join(filtered_lines) + '\n')
        
        print("✅ Email configuration saved!")
        print("\n🔄 Restart your Second Brain server to apply changes")
        
        if choice != "5":
            print(f"\n🧪 Test your setup:")
            print("1. Restart the server")
            print("2. Go to /login page")
            print("3. Try the magic link login with your email")

def show_email_status():
    """Show current email configuration status"""
    try:
        from config import settings
        from email_service import email_service
        
        print("📧 Current Email Configuration:")
        print(f"   Enabled: {settings.email_enabled}")
        print(f"   Service: {settings.email_service}")
        print(f"   From Email: {settings.email_from}")
        print(f"   From Name: {settings.email_from_name}")
        
        if settings.email_enabled:
            if email_service.test_connection():
                print("   ✅ Service is working")
            else:
                print("   ❌ Service connection failed")
        else:
            print("   📝 Magic links will be printed to console")
            
    except Exception as e:
        print(f"❌ Error checking email status: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        show_email_status()
    else:
        setup_email_service()