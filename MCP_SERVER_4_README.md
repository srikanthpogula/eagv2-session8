# MCP Server 4: Telegram, Web Search, Table Extraction, Google Drive, and Gmail Integration

## Overview

`mcp_server_4.py` provides a comprehensive set of MCP tools for:
1. **Telegram Message Processing** - Process messages from Telegram through the agent system
2. **Web Search** - Search the internet using DuckDuckGo
3. **Content Extraction** - Fetch and parse webpage content, including table detection
4. **Google Drive Integration** - Create Excel files from web content and upload to Google Drive
5. **Gmail Integration** - Send emails with Google Drive links

## Available Tools

### 1. `telegram_process_message`
Processes a Telegram message through the agent system. The agent intelligently decides what actions to take based on the message content.

**Usage:**
```
telegram_process_message|user_message="Extract table from https://example.com"
```

**Parameters:**
- `user_message` (required): The message from Telegram to process
- `config_path` (optional): Path to profiles.yaml (default: "config/profiles.yaml")

---

### 2. `web_search`
Searches the internet using DuckDuckGo and returns formatted results.

**Usage:**
```
web_search|query="Python programming tutorials"|max_results=5
```

**Parameters:**
- `query` (required): The search query string
- `max_results` (optional): Maximum number of results (default: 10)

---

### 3. `fetch_content`
Fetches and parses content from a webpage URL. Removes scripts/styles and returns clean text.

**Usage:**
```
fetch_content|url="https://example.com"
```

**Parameters:**
- `url` (required): The webpage URL to fetch

---

### 4. `gdrive_create_excel_from_web`
Extracts tables or structured data from a webpage and creates an Excel file on Google Drive.

**Usage:**
```
gdrive_create_excel_from_web|url="https://example.com/data"|query="extract the table"
```

**Parameters:**
- `url` (required): The webpage URL to extract content from
- `query` (required): Description of what content to extract
- `filename` (optional): Name for the Excel file (auto-generated if not provided)
- `folder_id` (optional): Google Drive folder ID
- `credentials_path` (optional): Path to Google OAuth credentials

**Features:**
- Automatically detects HTML tables
- If no tables found, extracts text content and organizes it in Excel
- Returns a shareable Google Drive link

---

### 5. `gmail_send_with_drive_link`
Sends an email via Gmail with a link to a Google Drive file.

**Usage:**
```
gmail_send_with_drive_link|to_email="user@example.com"|subject="Your file"|drive_link="https://drive.google.com/..."
```

**Parameters:**
- `to_email` (required): Recipient email address
- `subject` (required): Email subject line
- `drive_link` (required): Google Drive file link
- `body_text` (optional): Additional email body text
- `credentials_path` (optional): Path to Google OAuth credentials

---

### 6. `extract_table_to_drive_and_email`
Complete workflow function that combines table extraction, Google Drive upload, and email sending.

**Usage:**
```
extract_table_to_drive_and_email|url="https://example.com/data"|email="user@example.com"
```

**Parameters:**
- `url` (required): The webpage URL to extract table from
- `email` (optional): Email address to send Drive link to (default: srikanthpogula6001@gmail.com)
- `query` (optional): Description of what to extract (default: "extract the table")
- `filename` (optional): Name for the Excel file
- `folder_id` (optional): Google Drive folder ID
- `credentials_path` (optional): Path to Google OAuth credentials

**Workflow:**
1. Fetches the webpage
2. Detects and extracts tables (or structured data)
3. Creates Excel file on Google Drive
4. Emails the Drive link to the specified email

---

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `pandas` - For Excel file creation
- `openpyxl` - Excel file format support
- `google-api-python-client` - Google APIs
- `google-auth-httplib2` - Google authentication
- `google-auth-oauthlib` - OAuth flow
- `python-telegram-bot` - Telegram bot support
- `httpx` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- `mcp` - MCP framework

### 2. Google OAuth Setup

1. **Create Google Cloud Project:**
   - Go to https://console.cloud.google.com/
   - Create a new project or select existing

2. **Enable APIs:**
   - Enable **Google Drive API**
   - Enable **Gmail API**

3. **Configure OAuth Consent Screen:**
   - Go to APIs & Services → OAuth consent screen
   - Set user type (External or Internal)
   - Add scopes:
     - `https://www.googleapis.com/auth/drive.file`
     - `https://www.googleapis.com/auth/gmail.send`
   - Add test users (your email address)

4. **Create OAuth 2.0 Credentials:**
   - Go to APIs & Services → Credentials
   - Create OAuth client ID → Desktop app
   - Download credentials JSON file
   - Save as `credentials.json` in the project root or `~/.config/google/credentials.json`

### 3. Telegram Bot Setup (Optional)

If you want to use Telegram integration:

1. **Create a Telegram Bot:**
   - Message @BotFather on Telegram
   - Send `/newbot` and follow instructions
   - Save the bot token

2. **Create Telegram Bot Listener:**
   - Create a separate script (e.g., `telegram_bot_listener.py`) that:
     - Uses `python-telegram-bot` library
     - Listens for messages
     - Calls `telegram_process_message` tool when messages are received

### 4. Configuration

The server is already added to `config/profiles.yaml`:

```yaml
mcp_servers:
  - id: telegram-gdrive-gmail
    script: mcp_server_4.py
    cwd: C:/EAG/Session8/code2
```

---

## Usage Examples

### Example 1: Complete Workflow
```
User: "Extract the table from https://example.com/data and email it to me"

Agent Flow:
1. Calls extract_table_to_drive_and_email
2. Tool fetches webpage, extracts table
3. Creates Excel on Google Drive
4. Sends email with Drive link
```

### Example 2: Step-by-Step
```
User: "Search for Python tutorials, then get the first result and extract any tables"

Agent Flow:
1. Calls web_search|query="Python tutorials"
2. Gets results, extracts first URL
3. Calls fetch_content|url="..."
4. Detects table, calls gdrive_create_excel_from_web
5. Calls gmail_send_with_drive_link
```

### Example 3: Telegram Integration
```
Telegram Message: "https://example.com/data"

Agent Flow:
1. telegram_process_message receives message
2. Agent detects URL in message
3. Calls extract_table_to_drive_and_email
4. Returns result to Telegram user
```

---

## File Structure

```
code2/
├── mcp_server_4.py          # Main MCP server file
├── config/
│   └── profiles.yaml        # Updated with mcp_server_4
├── requirements.txt         # Dependencies
└── credentials.json         # Google OAuth credentials (user-provided)
```

---

## Authentication Files

The server looks for Google credentials in this order:
1. `credentials_path` parameter (if provided)
2. `~/.config/google/credentials.json` (environment default)
3. `credentials.json` (project root)

Token files are saved as:
- `~/.config/google/token_drive.json` (Drive)
- `~/.config/google/token_gmail.json` (Gmail)

Or in project root:
- `token_drive.json`
- `token_gmail.json`

---

## Error Handling

The server includes comprehensive error handling:
- **Missing Google APIs**: Returns helpful error message with installation instructions
- **Network errors**: Handles timeouts and HTTP errors gracefully
- **OAuth errors**: Provides clear error messages for credential issues
- **Table extraction**: Falls back to text extraction if no tables found

---

## Notes

1. **Rate Limiting**: Web search and content fetching include rate limiting (30 requests/minute for search, 20 for content)

2. **Table Detection**: The tool automatically detects HTML tables. If none are found, it extracts text content and organizes it in Excel format.

3. **Excel File Naming**: If filename is not provided, it's auto-generated using domain name and timestamp.

4. **File Sharing**: Excel files uploaded to Google Drive are automatically made shareable (anyone with link can view).

5. **Email Default**: The default email address is `srikanthpogula6001@gmail.com` if not specified.

---

## Troubleshooting

### "Google APIs not available"
- Install: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`

### "Credentials file not found"
- Download OAuth credentials from Google Cloud Console
- Save as `credentials.json` in project root or `~/.config/google/`

### "Access blocked" during OAuth
- Ensure OAuth consent screen is configured
- Add your email as a test user
- Set publishing status to "Testing"

### "No tables found"
- The tool will extract text content instead
- Check if the webpage actually contains HTML tables
- Some tables may be dynamically loaded (JavaScript) and won't be detected

---

## Integration with Agent System

The tools in `mcp_server_4.py` are designed to work seamlessly with the agent system in `code2/`. The agent can:

1. **Intelligently decide** which tools to use based on user input
2. **Chain multiple tools** together (e.g., search → fetch → extract → email)
3. **Handle errors** and provide meaningful feedback
4. **Use memory** to remember previous tool results

The agent's planning module (`modules/decision.py`) will automatically have access to these tools when `mcp_server_4.py` is configured in `profiles.yaml`.

