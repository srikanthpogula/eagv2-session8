# Telegram Bot Setup Guide

## Quick Start

### 1. Get Your Bot Token

1. **Open Telegram** (on your phone or laptop)
2. **Search for @BotFather**
3. **Send**: `/newbot`
4. **Follow the prompts**:
   - Bot name: `My Agent Bot` (or any name)
   - Bot username: `my_agent_bot` (must end with 'bot')
5. **Copy the token** you receive (looks like: `123456789:ABCdef...`)

### 2. Configure the Bot Token

Edit `telegram_bot_listener.py` and replace:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

with your actual token:
```python
BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
```

### 3. Install Dependencies

Make sure all dependencies are installed in your `uv` environment:
```powershell
uv pip install python-telegram-bot
```

Or sync all dependencies:
```powershell
uv sync
```

### 4. Run the Telegram Bot

Instead of running `agent.py`, run:
```powershell
uv run telegram_bot_listener.py
```

Or:
```powershell
python telegram_bot_listener.py
```

### 5. Use the Bot

1. **Search for your bot** in Telegram using the username you created
2. **Start a conversation** with your bot
3. **Send `/start`** to see the welcome message
4. **Send your queries** - the agent will process them!

## How It Works

- The bot listens for messages in Telegram
- When you send a message, it processes it through the agent system
- The agent intelligently decides what tools to use
- Results are sent back to you in Telegram

## Example Queries

- `Extract table from https://www.formula1.com/en/results/2025/drivers and email it`
- `Get data from https://example.com and save to Drive`
- `Search for Python programming tutorials`
- `What is the relationship between X and Y?`

## Commands

- `/start` - Welcome message and instructions
- `/help` - Help and examples

## Notes

- The bot processes messages through the full agent system
- All MCP tools are available (web search, GDrive, Gmail, etc.)
- Long responses are automatically split (Telegram has 4096 char limit)
- The bot runs continuously until you stop it (Ctrl+C)

