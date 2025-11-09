"""
Telegram Bot Listener for Agent Integration

This script listens for Telegram messages and processes them through the agent system.
"""

import asyncio
import sys
from pathlib import Path

# Add the code directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
except ImportError:
    print("ERROR: python-telegram-bot not installed!")
    print("Install it with: uv pip install python-telegram-bot")
    sys.exit(1)

import yaml
from core.loop import AgentLoop
from core.session import MultiMCP

# ============================================
# CONFIGURATION - REPLACE WITH YOUR BOT TOKEN
# ============================================
# Get your bot token from @BotFather on Telegram
BOT_TOKEN = "BOT Token Here"  # Replace this with your actual bot token!

# ============================================


async def execute_agent(
    user_input: str, config_path: str = "config/profiles.yaml"
) -> str:
    """
    Execute agent with given user input. This is the core agent execution function
    used by the Telegram bot listener.

    Args:
        user_input: The user's query/message to process
        config_path: Path to profiles.yaml config file (default: "config/profiles.yaml")

    Returns:
        Final result from agent execution
    """
    try:
        print(f"[INFO] Processing query: {user_input[:100]}...")

        # Load MCP server configs
        config_file = Path(config_path)
        if not config_file.exists():
            error_msg = f"Error: Config file not found at {config_path}"
            print(f"[ERROR] {error_msg}")
            return error_msg

        with config_file.open("r") as f:
            profile = yaml.safe_load(f)
            mcp_servers = profile.get("mcp_servers", [])

        # Initialize MultiMCP
        multi_mcp = MultiMCP(server_configs=mcp_servers)
        await multi_mcp.initialize()
        print("[INFO] MCP servers initialized")

        # Create and run agent
        agent = AgentLoop(user_input=user_input, dispatcher=multi_mcp)
        print("[INFO] Agent loop created, starting execution...")

        final_response = await agent.run()
        result = final_response.replace("FINAL_ANSWER:", "").strip()

        print(f"[INFO] Agent execution completed. Result: {result[:200]}...")
        return result
    except Exception as e:
        error_msg = f"Error executing agent: {str(e)}"
        print(f"[ERROR] {error_msg}")
        import traceback

        traceback.print_exc(file=sys.stderr)
        return error_msg


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Telegram messages"""
    if not update.message or not update.message.text:
        return

    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"

    print(f"\n{'=' * 60}")
    print(f"Received message from user {user_id} (@{username})")
    print(f"Message: {user_message}")
    print(f"{'=' * 60}\n")

    # Send "processing" message
    processing_msg = await update.message.reply_text("🔄 Processing your request...")

    try:
        # Execute the agent
        result = await execute_agent(user_message, config_path="config/profiles.yaml")

        # Telegram has a 4096 character limit per message
        # Split long messages if needed
        if len(result) > 4000:
            # Send first part
            await processing_msg.edit_text(f"✅ Result:\n{result[:4000]}")
            # Send remaining parts
            remaining = result[4000:]
            while remaining:
                await update.message.reply_text(remaining[:4000])
                remaining = remaining[4000:]
        else:
            await processing_msg.edit_text(f"✅ Result:\n{result}")

        print(f"✅ Successfully processed message for user {user_id}")

    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        print(f"ERROR: {error_msg}")

        # Send error message
        if len(error_msg) > 4000:
            await processing_msg.edit_text(f"❌ Error:\n{error_msg[:4000]}")
        else:
            await processing_msg.edit_text(error_msg)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = (
        "🤖 Agent Bot Ready!\n\n"
        "I can help you:\n"
        "• Process queries through the agent system\n"
        "• Extract tables from web pages\n"
        "• Create Excel files on Google Drive\n"
        "• Send emails with Drive links\n"
        "• Search the internet\n\n"
        "📋 Quick Workflow:\n"
        "Send me a URL with a table and I'll:\n"
        "1. Extract the table\n"
        "2. Create Excel on Google Drive\n"
        "3. Email you the link\n\n"
        "Example:\n"
        "'Extract the table from https://example.com/data'\n"
        "or\n"
        "'Get table from https://example.com and email to srikanthpogula6001@gmail.com'"
    )
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = (
        "📖 Help\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n\n"
        "🔄 Automatic Workflow:\n"
        "If you send a message with a URL, I'll intelligently:\n"
        "1. Extract tables or data from the webpage\n"
        "2. Create Excel file on Google Drive\n"
        "3. Email the link to srikanthpogula6001@gmail.com\n\n"
        "Examples:\n"
        "• 'Extract the table from https://example.com/data'\n"
        "• 'Get table from https://example.com and email to srikanthpogula6001@gmail.com'\n"
        "• 'What is the relationship between X and Y?' (general query)\n"
        "• 'Search for information about Python programming' (general query)\n"
        "• 'https://www.formula1.com/en/results/2025/drivers' (just a URL - I'll figure it out!)"
    )
    await update.message.reply_text(help_message)


def main():
    """Start the Telegram bot"""
    # Check if bot token is set
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("=" * 60)
        print("ERROR: Bot token not configured!")
        print("=" * 60)
        print("\nPlease edit telegram_bot_listener.py and replace:")
        print("  BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'")
        print("\nwith your actual bot token from @BotFather")
        print("\nTo get a bot token:")
        print("1. Open Telegram")
        print("2. Search for @BotFather")
        print("3. Send /newbot and follow instructions")
        print("4. Copy the token you receive")
        print("=" * 60)
        sys.exit(1)

    print("=" * 60)
    print("Starting Telegram Bot...")
    print("=" * 60)
    print(f"Bot token: {BOT_TOKEN[:10]}...{BOT_TOKEN[-5:]}")
    print("=" * 60)

    try:
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        # Use post_init to show bot info after initialization
        # This avoids event loop conflicts
        async def post_init(app: Application) -> None:
            bot_info = await app.bot.get_me()
            print(f"\n✅ Bot initialized!")
            print(f"   Bot name: {bot_info.first_name}")
            print(f"   Bot username: @{bot_info.username}")
            print(f"   📱 Search for: @{bot_info.username} in Telegram")
            print("   Send /start to begin!")
            print("\n" + "=" * 60 + "\n")

        application.post_init = post_init

        print(f"\n✅ Starting bot...")
        print("   (Initializing connection...)\n")

        # Start polling
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        print(f"\n❌ Error starting bot: {e}")
        print("\nTroubleshooting:")
        print("1. Check that your bot token is correct")
        print(
            "2. Make sure python-telegram-bot is installed: uv pip install python-telegram-bot"
        )
        print("3. Check your internet connection")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
        sys.exit(0)
