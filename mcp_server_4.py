"""
MCP Server 4: Telegram, Web Search, Table Extraction, Google Drive, and Gmail Integration

This server provides tools for:
- Processing Telegram messages
- Searching the internet
- Extracting content (including tables) from webpages
- Creating Excel files on Google Drive
- Sending emails with Drive links
"""

from mcp.server.fastmcp import FastMCP, Context
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional
from dataclasses import dataclass
import urllib.parse
import sys
import traceback
import asyncio
from datetime import datetime, timedelta
import re
import yaml
from pathlib import Path
import pandas as pd
from io import BytesIO
import base64
import email.mime.text

# Google APIs
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    GOOGLE_APIS_AVAILABLE = True
except ImportError as e:
    GOOGLE_APIS_AVAILABLE = False
    # Log the import error for debugging
    import sys
    print(f"[mcp_server_4] WARNING: Google APIs import failed: {e}", file=sys.stderr)
    print(f"[mcp_server_4] Python path: {sys.path}", file=sys.stderr)
    print(f"[mcp_server_4] Python executable: {sys.executable}", file=sys.stderr)

# Telegram
try:
    from telegram import Update
    from telegram.ext import Application, MessageHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False


@dataclass
class SearchResult:
    title: str
    link: str
    snippet: str
    position: int


class RateLimiter:
    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.requests = []

    async def acquire(self):
        now = datetime.now()
        # Remove requests older than 1 minute
        self.requests = [
            req for req in self.requests if now - req < timedelta(minutes=1)
        ]

        if len(self.requests) >= self.requests_per_minute:
            # Wait until we can make another request
            wait_time = 60 - (now - self.requests[0]).total_seconds()
            if wait_time > 0:
                await asyncio.sleep(wait_time)

        self.requests.append(now)


class DuckDuckGoSearcher:
    BASE_URL = "https://html.duckduckgo.com/html"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    def __init__(self):
        self.rate_limiter = RateLimiter()

    def format_results_for_llm(self, results: List[SearchResult]) -> str:
        """Format results in a natural language style that's easier for LLMs to process"""
        if not results:
            return "No results were found for your search query. This could be due to DuckDuckGo's bot detection or the query returned no matches. Please try rephrasing your search or try again in a few minutes."

        output = []
        output.append(f"Found {len(results)} search results:\n")

        for result in results:
            output.append(f"{result.position}. {result.title}")
            output.append(f"   URL: {result.link}")
            output.append(f"   Summary: {result.snippet}")
            output.append("")  # Empty line between results

        return "\n".join(output)

    async def search(
        self, query: str, ctx: Context, max_results: int = 10
    ) -> List[SearchResult]:
        try:
            # Apply rate limiting
            await self.rate_limiter.acquire()

            # Create form data for POST request
            data = {
                "q": query,
                "b": "",
                "kl": "",
            }

            await ctx.info(f"Searching DuckDuckGo for: {query}")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.BASE_URL, data=data, headers=self.HEADERS, timeout=30.0
                )
                response.raise_for_status()

            # Parse HTML response
            soup = BeautifulSoup(response.text, "html.parser")
            if not soup:
                await ctx.error("Failed to parse HTML response")
                return []

            results = []
            for result in soup.select(".result"):
                title_elem = result.select_one(".result__title")
                if not title_elem:
                    continue

                link_elem = title_elem.find("a")
                if not link_elem:
                    continue

                title = link_elem.get_text(strip=True)
                link = link_elem.get("href", "")

                # Skip ad results
                if "y.js" in link:
                    continue

                # Clean up DuckDuckGo redirect URLs
                if link.startswith("//duckduckgo.com/l/?uddg="):
                    link = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])

                snippet_elem = result.select_one(".result__snippet")
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                results.append(
                    SearchResult(
                        title=title,
                        link=link,
                        snippet=snippet,
                        position=len(results) + 1,
                    )
                )

                if len(results) >= max_results:
                    break

            await ctx.info(f"Successfully found {len(results)} results")
            return results

        except httpx.TimeoutException:
            await ctx.error("Search request timed out")
            return []
        except httpx.HTTPError as e:
            await ctx.error(f"HTTP error occurred: {str(e)}")
            return []
        except Exception as e:
            await ctx.error(f"Unexpected error during search: {str(e)}")
            traceback.print_exc(file=sys.stderr)
            return []


class WebContentFetcher:
    def __init__(self):
        self.rate_limiter = RateLimiter(requests_per_minute=20)

    async def fetch_and_parse(self, url: str, ctx: Context) -> str:
        """Fetch and parse content from a webpage"""
        try:
            await self.rate_limiter.acquire()

            await ctx.info(f"Fetching content from: {url}")

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    },
                    follow_redirects=True,
                    timeout=30.0,
                )
                response.raise_for_status()

            # Parse the HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()

            # Get the text content
            text = soup.get_text()

            # Clean up the text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = " ".join(chunk for chunk in chunks if chunk)

            # Remove extra whitespace
            text = re.sub(r"\s+", " ", text).strip()

            # Truncate if too long
            if len(text) > 8000:
                text = text[:8000] + "... [content truncated]"

            await ctx.info(
                f"Successfully fetched and parsed content ({len(text)} characters)"
            )
            return text

        except httpx.TimeoutException:
            await ctx.error(f"Request timed out for URL: {url}")
            return "Error: The request timed out while trying to fetch the webpage."
        except httpx.HTTPError as e:
            await ctx.error(f"HTTP error occurred while fetching {url}: {str(e)}")
            return f"Error: Could not access the webpage ({str(e)})"
        except Exception as e:
            await ctx.error(f"Error fetching content from {url}: {str(e)}")
            return f"Error: An unexpected error occurred while fetching the webpage ({str(e)})"


# ==================== Google Services Helper Classes ====================


class GoogleDriveService:
    """Helper class for Google Drive operations"""

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]

    def __init__(self, credentials_path: str = None, token_path: str = None):
        # Use environment variable or default, but convert to Path
        env_creds = Path.home() / ".config" / "google" / "credentials.json"
        default_creds = Path("credentials.json")
        self.credentials_path = Path(
            credentials_path or (env_creds if env_creds.exists() else default_creds)
        )

        env_token = Path.home() / ".config" / "google" / "token_drive.json"
        default_token = Path("token_drive.json")
        self.token_path = Path(
            token_path or (env_token if env_token.exists() else default_token)
        )
        self.service = None

    def _get_credentials(self):
        """Get valid user credentials from storage or OAuth flow"""
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), self.SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found: {self.credentials_path}. "
                        "Please download OAuth2 credentials from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), self.SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        return creds

    def get_service(self):
        """Get Drive service instance"""
        # Check dynamically instead of relying on module-level variable
        try:
            from googleapiclient.discovery import build
        except ImportError as e:
            raise ImportError(
                f"Google APIs not available. Install: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\nImport error: {e}"
            )

        if self.service is None:
            creds = self._get_credentials()
            self.service = build("drive", "v3", credentials=creds)
        return self.service

    async def upload_excel(
        self, excel_data: BytesIO, filename: str, folder_id: str = None
    ) -> str:
        """Upload Excel file to Google Drive and return file ID"""
        try:
            # Run sync operations in executor to avoid blocking
            loop = asyncio.get_event_loop()
            service = await loop.run_in_executor(None, self.get_service)

            file_metadata = {"name": filename}
            if folder_id:
                file_metadata["parents"] = [folder_id]

            excel_data.seek(0)
            media = MediaIoBaseUpload(
                excel_data,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                resumable=True,
            )

            # Execute API calls in executor
            file = await loop.run_in_executor(
                None,
                lambda: service.files()
                .create(body=file_metadata, media_body=media, fields="id, webViewLink")
                .execute(),
            )

            # Make file shareable
            permission = {"type": "anyone", "role": "reader"}
            await loop.run_in_executor(
                None,
                lambda: service.permissions()
                .create(fileId=file.get("id"), body=permission)
                .execute(),
            )

            return file.get(
                "webViewLink", f"https://drive.google.com/file/d/{file.get('id')}/view"
            )
        except Exception as e:
            raise Exception(f"Failed to upload to Google Drive: {str(e)}")


class GmailService:
    """Helper class for Gmail operations"""

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    def __init__(self, credentials_path: str = None, token_path: str = None):
        # Use environment variable or default, but convert to Path
        env_creds = Path.home() / ".config" / "google" / "credentials.json"
        default_creds = Path("credentials.json")
        self.credentials_path = Path(
            credentials_path or (env_creds if env_creds.exists() else default_creds)
        )

        env_token = Path.home() / ".config" / "google" / "token_gmail.json"
        default_token = Path("token_gmail.json")
        self.token_path = Path(
            token_path or (env_token if env_token.exists() else default_token)
        )
        self.service = None

    def _get_credentials(self):
        """Get valid user credentials from storage or OAuth flow"""
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), self.SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found: {self.credentials_path}. "
                        "Please download OAuth2 credentials from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), self.SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        return creds

    def get_service(self):
        """Get Gmail service instance"""
        # Check dynamically instead of relying on module-level variable
        try:
            from googleapiclient.discovery import build
        except ImportError as e:
            raise ImportError(
                f"Google APIs not available. Install: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\nImport error: {e}"
            )

        if self.service is None:
            creds = self._get_credentials()
            self.service = build("gmail", "v1", credentials=creds)
        return self.service

    async def send_email(
        self, to_email: str, subject: str, body: str, ctx: Context
    ) -> str:
        """Send email via Gmail API"""
        try:
            # Run sync operations in executor to avoid blocking
            loop = asyncio.get_event_loop()
            service = await loop.run_in_executor(None, self.get_service)

            message = self._create_message(to_email, subject, body)
            sent_message = await loop.run_in_executor(
                None,
                lambda: service.users()
                .messages()
                .send(userId="me", body=message)
                .execute(),
            )

            await ctx.info(
                f"Email sent successfully. Message ID: {sent_message.get('id')}"
            )
            return f"Email sent successfully to {to_email}"
        except Exception as e:
            await ctx.error(f"Failed to send email: {str(e)}")
            raise Exception(f"Failed to send email: {str(e)}")

    def _create_message(self, to: str, subject: str, body: str) -> dict:
        """Create email message"""
        message = email.mime.text.MIMEText(body, "html")
        message["to"] = to
        message["subject"] = subject
        return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}


# Initialize FastMCP server
mcp = FastMCP("telegram-gdrive-gmail")
searcher = DuckDuckGoSearcher()
fetcher = WebContentFetcher()


# ==================== MCP Tools ====================


@mcp.tool()
async def telegram_process_message(
    user_message: str, ctx: Context, config_path: str = "config/profiles.yaml"
) -> str:
    """
    Process a message from Telegram and execute it through the agent flow.
    The agent will intelligently decide what actions to take based on the message.
    For example, if the message contains a URL, the agent may search the internet,
    fetch the page, check for tables, and if found, extract them to Excel on Google Drive
    and email the link.

    Note: This function processes the message. The actual Telegram bot listener should be set up separately
    to call this function when messages are received.

    Args:
        user_message: The message received from Telegram to process
        ctx: MCP context for logging
        config_path: Path to profiles.yaml config file (default: "config/profiles.yaml")

    Returns:
        Result from agent execution

    Usage: telegram_process_message|user_message="Extract table from https://example.com"
    """
    await ctx.info("Processing Telegram message through intelligent agent system...")

    try:
        # Import agent components
        from core.loop import AgentLoop
        from core.session import MultiMCP

        # Load MCP server configs
        config_file = Path(config_path)
        if not config_file.exists():
            error_msg = f"Error: Config file not found at {config_path}"
            await ctx.error(error_msg)
            return error_msg

        with config_file.open("r") as f:
            profile = yaml.safe_load(f)
            mcp_servers = profile.get("mcp_servers", [])

        # Initialize MultiMCP
        multi_mcp = MultiMCP(server_configs=mcp_servers)
        await multi_mcp.initialize()
        await ctx.info("MCP servers initialized")

        # Create and run agent
        agent = AgentLoop(user_input=user_message, dispatcher=multi_mcp)
        await ctx.info("Agent loop created, starting execution...")

        final_response = await agent.run()
        result = final_response.replace("FINAL_ANSWER:", "").strip()

        await ctx.info(f"Agent execution completed. Result: {result[:200]}...")
        return f"Agent executed successfully. Result: {result}"

    except Exception as e:
        error_msg = f"Error executing agent: {str(e)}"
        await ctx.error(error_msg)
        traceback.print_exc(file=sys.stderr)
        return error_msg


# Initialize FastMCP server
mcp = FastMCP("telegram-gdrive-gmail")
searcher = DuckDuckGoSearcher()
fetcher = WebContentFetcher()


# ==================== MCP Tools ====================


@mcp.tool()
async def web_search(query: str, ctx: Context, max_results: int = 10) -> str:
    """
    Search DuckDuckGo and return formatted results.

    Use this tool when:
    - User asks to search the internet
    - User wants to find information online
    - User provides a search query

    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 10)
        ctx: MCP context for logging

    Returns:
        Formatted search results

    Usage: web_search|query="Python programming tutorials"|max_results=5
    """
    try:
        results = await searcher.search(query, ctx, max_results)
        return searcher.format_results_for_llm(results)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return f"An error occurred while searching: {str(e)}"


@mcp.tool()
async def fetch_content(url: str, ctx: Context) -> str:
    """
    Fetch and parse content from a webpage URL.

    Use this tool when:
    - User provides a URL and you need to see what's on the page
    - You need to check if a webpage contains tables or structured data
    - You want to read webpage content before deciding next steps

    This tool fetches the webpage, removes scripts/styles, and returns clean text content.
    After fetching, you can decide if the page contains tables and use gdrive_create_excel_from_web if needed.

    Args:
        url: The webpage URL to fetch content from
        ctx: MCP context for logging

    Returns:
        Clean text content from the webpage

    Usage: fetch_content|url="https://example.com"
    """
    return await fetcher.fetch_and_parse(url, ctx)


@mcp.tool()
async def gdrive_create_excel_from_web(
    url: str,
    query: str,
    ctx: Context,
    filename: str = None,
    folder_id: str = None,
    credentials_path: str = None,
) -> str:
    """
    Extract table or structured data from a webpage and create Excel file on Google Drive.

    Use this tool when:
    - User provides a URL and wants data extracted from it
    - The webpage contains tables or structured data
    - You need to save webpage data to Excel format

    The tool will automatically detect and extract HTML tables from the webpage.
    If no tables are found, it will extract text content and organize it in Excel format.

    Returns a Google Drive link to the created Excel file.

    Args:
        url: The webpage URL to extract content from
        query: Description of what content to extract (e.g., "extract the table", "get the data table")
        filename: Name for the Excel file (default: auto-generated)
        folder_id: Google Drive folder ID (optional)
        credentials_path: Path to Google OAuth credentials (or set GOOGLE_CREDENTIALS_PATH env var)

    Returns:
        Success message with Google Drive link

    Usage: gdrive_create_excel_from_web|url="https://example.com/data"|query="extract the table"
    """
    # Check Google APIs availability dynamically (in case import failed at module level)
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        google_apis_available = True
    except ImportError as import_err:
        google_apis_available = False
        await ctx.error(f"Google APIs import failed: {import_err}")
        return f"Error: Google APIs not installed. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\nImport error: {import_err}"

    if not google_apis_available:
        return "Error: Google APIs not installed. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"

    try:
        await ctx.info(f"Fetching webpage: {url}")

        # Fetch webpage content
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                follow_redirects=True,
                timeout=30.0,
            )
            response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Try to find tables
        tables = soup.find_all("table")

        if not tables:
            # If no tables found, try to extract structured data or create from text
            await ctx.info("No tables found. Extracting text content...")
            text_content = soup.get_text(separator="\n", strip=True)

            # Create a simple Excel with the text content
            df = pd.DataFrame(
                {
                    "Content": [
                        line for line in text_content.split("\n") if line.strip()
                    ][:1000]  # Limit rows
                }
            )
        else:
            # Extract first table or all tables
            await ctx.info(f"Found {len(tables)} table(s). Extracting...")

            if len(tables) == 1:
                df = pd.read_html(str(tables[0]))[0]
            else:
                # Combine multiple tables or use the first one
                df = pd.read_html(str(tables[0]))[0]
                await ctx.info(f"Using first table with {len(df)} rows")

        # Generate filename if not provided
        if not filename:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc.replace(".", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"extracted_data_{domain}_{timestamp}.xlsx"

        if not filename.endswith(".xlsx"):
            filename += ".xlsx"

        # Create Excel in memory
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        excel_buffer.seek(0)

        await ctx.info(
            f"Created Excel file with {len(df)} rows. Uploading to Google Drive..."
        )

        # Upload to Google Drive
        drive_service = GoogleDriveService(credentials_path=credentials_path)
        drive_link = await drive_service.upload_excel(excel_buffer, filename, folder_id)

        await ctx.info(f"Successfully uploaded to Google Drive: {drive_link}")
        return f"Excel file created and uploaded to Google Drive. Link: {drive_link}"

    except Exception as e:
        await ctx.error(f"Error creating Excel from web: {str(e)}")
        traceback.print_exc(file=sys.stderr)
        return f"Error: {str(e)}"


@mcp.tool()
async def gmail_send_with_drive_link(
    to_email: str,
    subject: str,
    drive_link: str,
    ctx: Context,
    body_text: str = None,
    credentials_path: str = None,
) -> str:
    """
    Send an email via Gmail with a link to a Google Drive file.

    Use this tool when:
    - User wants to email a Google Drive link
    - You've created a file on Google Drive and need to share it via email
    - User requests to "send" or "email" a file or link

    The default email address is srikanthpogula6001@gmail.com if not specified.

    Args:
        to_email: Recipient email address (default: srikanthpogula6001@gmail.com if not specified)
        subject: Email subject line
        drive_link: Google Drive file link
        ctx: MCP context for logging
        body_text: Additional email body text (optional)
        credentials_path: Path to Google OAuth credentials (or set GOOGLE_CREDENTIALS_PATH env var)

    Returns:
        Success message

    Usage: gmail_send_with_drive_link|to_email="user@example.com"|subject="Your file"|drive_link="https://drive.google.com/..."
    """
    # Check Google APIs availability dynamically (in case import failed at module level)
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        google_apis_available = True
    except ImportError as import_err:
        google_apis_available = False
        await ctx.error(f"Google APIs import failed: {import_err}")
        return f"Error: Google APIs not installed. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\nImport error: {import_err}"

    if not google_apis_available:
        return "Error: Google APIs not installed. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"

    try:
        # Create email body
        if body_text:
            body = f"""
            <html>
            <body>
            <p>{body_text}</p>
            <p>You can access the file here: <a href="{drive_link}">{drive_link}</a></p>
            </body>
            </html>
            """
        else:
            body = f"""
            <html>
            <body>
            <p>Please find the requested file on Google Drive:</p>
            <p><a href="{drive_link}">Open File</a></p>
            <p>Direct link: {drive_link}</p>
            </body>
            </html>
            """

        gmail_service = GmailService(credentials_path=credentials_path)
        result = await gmail_service.send_email(to_email, subject, body, ctx)

        await ctx.info(f"Email sent successfully to {to_email}")
        return result

    except Exception as e:
        await ctx.error(f"Error sending email: {str(e)}")
        traceback.print_exc(file=sys.stderr)
        return f"Error: {str(e)}"


@mcp.tool()
async def extract_table_to_drive_and_email(
    url: str,
    ctx: Context,
    email: str = "srikanthpogula6001@gmail.com",
    query: str = "extract the table",
    user_query: str = None,
    filename: str = None,
    folder_id: str = None,
    credentials_path: str = None,
) -> str:
    """
    Complete workflow: Extract table from webpage, create Excel on Google Drive, and send email.
    This is a convenience function that combines gdrive_create_excel_from_web and gmail_send_with_drive_link.

    Use this tool when:
    - User provides a URL and wants data extracted and emailed
    - User asks to "get data from URL" or "extract information from webpage"
    - User wants data from a webpage saved to Excel and emailed
    - The webpage likely contains tables or structured data

    This tool automatically:
    1. Fetches the webpage
    2. Detects and extracts tables (or structured data)
    3. Creates Excel file on Google Drive
    4. Emails the Drive link to the specified email (default: srikanthpogula6001@gmail.com)

    The agent should use this tool when a user provides a URL and wants data extracted, even if they don't explicitly mention "table" or "excel".

    Args:
        url: The webpage URL to extract table from
        ctx: MCP context for logging
        email: Email address to send the Drive link to (default: srikanthpogula6001@gmail.com)
        query: Description of what to extract (default: "extract the table")
        user_query: Original user query from Telegram (optional, used for email subject)
        filename: Name for the Excel file (optional, auto-generated if not provided)
        folder_id: Google Drive folder ID (optional)
        credentials_path: Path to Google OAuth credentials (optional)

    Returns:
        Success message with Drive link

    Usage: extract_table_to_drive_and_email|url="https://example.com/data"|email="user@example.com"|user_query="Extract table from URL and email it"
    """
    try:
        await ctx.info("Starting complete workflow: Extract table → Drive → Email")
        await ctx.info(f"URL: {url}")
        await ctx.info(f"Email: {email}")
        
        # Use user_query if provided, otherwise fall back to query
        email_subject_query = user_query if user_query else query

        # Step 1: Extract table and create Excel on Google Drive
        await ctx.info("Step 1: Extracting table and creating Excel on Google Drive...")
        drive_result = await gdrive_create_excel_from_web(
            url=url,
            query=query,
            ctx=ctx,
            filename=filename,
            folder_id=folder_id,
            credentials_path=credentials_path,
        )

        # Check if drive_result contains an error
        if "Error:" in drive_result or "not installed" in drive_result.lower():
            error_msg = f"Failed to create Excel on Google Drive: {drive_result}"
            await ctx.error(error_msg)
            return f"❌ {error_msg}"

        # Extract Drive link from result
        if "Link:" in drive_result:
            drive_link = drive_result.split("Link:")[-1].strip()
        elif "https://drive.google.com" in drive_result:
            # Extract URL from the result string
            urls = re.findall(r"https://drive\.google\.com[^\s]+", drive_result)
            drive_link = urls[0] if urls else drive_result
        else:
            # If no clear link found, treat as error
            error_msg = f"Could not extract Drive link from result: {drive_result}"
            await ctx.error(error_msg)
            return f"❌ {error_msg}"

        await ctx.info(f"Step 1 complete. Drive link: {drive_link}")

        # Step 2: Send email with Drive link
        await ctx.info("Step 2: Sending email with Drive link...")
        
        # Create email subject with user query
        # Truncate user query if too long (email subjects should be reasonable length)
        subject_query = email_subject_query[:100] if len(email_subject_query) > 100 else email_subject_query
        email_subject = f"Results for your query: {subject_query}"
        
        email_result = await gmail_send_with_drive_link(
            to_email=email,
            subject=email_subject,
            drive_link=drive_link,
            ctx=ctx,
            body_text=f"The table has been extracted from {url} and saved to Google Drive.",
            credentials_path=credentials_path,
        )

        # Check if email sending failed
        if "Error:" in email_result or "not installed" in email_result.lower():
            error_msg = f"Failed to send email: {email_result}"
            await ctx.error(error_msg)
            return f"⚠️ Excel file created on Google Drive, but email failed:\n🔗 Drive link: {drive_link}\n❌ Email error: {email_result}"

        await ctx.info("Step 2 complete. Email sent successfully.")

        return f"✅ Complete workflow finished successfully!\n\n📊 Excel file created on Google Drive\n📧 Email sent to {email}\n🔗 Drive link: {drive_link}"

    except Exception as e:
        error_msg = f"Error in complete workflow: {str(e)}"
        await ctx.error(error_msg)
        traceback.print_exc(file=sys.stderr)
        return f"❌ {error_msg}"


@mcp.tool()
async def extract_table_to_drive_and_email_sse(
    url: str,
    ctx: Context,
    email: str = "srikanthpogula6001@gmail.com",
    query: str = "extract the table",
    user_query: str = None,
    filename: str = None,
    folder_id: str = None,
    credentials_path: str = None,
    sse_port: int = 8001,
) -> str:
    """
    Complete workflow with SSE (Server-Sent Events) streaming: Extract table from webpage,
    create Excel on Google Drive, and send email. Streams progress updates in real-time via SSE.

    This is an SSE-enabled version of extract_table_to_drive_and_email that provides
    real-time progress updates during the workflow.

    Use this tool when:
    - User wants real-time progress updates during table extraction
    - You need to stream status updates to a web client or monitoring system
    - Long-running operations need progress feedback

    Args:
        url: The webpage URL to extract table from
        ctx: MCP context for logging
        email: Email address to send the Drive link to (default: srikanthpogula6001@gmail.com)
        query: Description of what to extract (default: "extract the table")
        user_query: Original user query from Telegram (optional, used for email subject)
        filename: Name for the Excel file (optional, auto-generated if not provided)
        folder_id: Google Drive folder ID (optional)
        credentials_path: Path to Google OAuth credentials (optional)
        sse_port: Port for SSE server (default: 8001)

    Returns:
        SSE endpoint URL and completion message

    Usage: extract_table_to_drive_and_email_sse|url="https://example.com/data"|user_query="Extract table and email it"
    """
    try:
        await ctx.info("Starting SSE-enabled workflow: Extract table → Drive → Email")
        
        # Import SSE server components
        try:
            from aiohttp import web
        except ImportError:
            error_msg = "Error: aiohttp not installed. Install with: pip install aiohttp"
            await ctx.error(error_msg)
            return error_msg

        # Create SSE event queue
        event_queue = asyncio.Queue()
        sse_url = f"http://localhost:{sse_port}/events"

        async def sse_handler(request):
            """SSE endpoint handler"""
            response = web.StreamResponse()
            response.headers["Content-Type"] = "text/event-stream"
            response.headers["Cache-Control"] = "no-cache"
            response.headers["Connection"] = "keep-alive"
            response.headers["Access-Control-Allow-Origin"] = "*"  # Allow CORS
            await response.prepare(request)

            while True:
                try:
                    # Wait for events with timeout
                    event_data = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    event_type = event_data.get("event", "message")
                    event_content = event_data.get("data", "")

                    # Format as SSE
                    sse_message = f"event: {event_type}\ndata: {event_content}\n\n"
                    await response.write(sse_message.encode("utf-8"))

                    if event_type == "complete":
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    await response.write(b"event: ping\ndata: \n\n")
                except Exception as e:
                    await ctx.error(f"SSE error: {str(e)}")
                    break

            return response

        async def run_workflow_with_sse():
            """Run workflow and send SSE events"""
            try:
                # Use user_query if provided, otherwise fall back to query
                email_subject_query = user_query if user_query else query
                
                await event_queue.put({
                    "event": "status",
                    "data": "Starting workflow: Extract table → Drive → Email"
                })
                await event_queue.put({
                    "event": "status",
                    "data": f"Fetching webpage: {url}"
                })

                # Step 1: Extract table and create Excel on Google Drive
                await event_queue.put({
                    "event": "status",
                    "data": "Step 1: Extracting table and creating Excel on Google Drive..."
                })
                
                drive_result = await gdrive_create_excel_from_web(
                    url=url,
                    query=query,
                    ctx=ctx,
                    filename=filename,
                    folder_id=folder_id,
                    credentials_path=credentials_path,
                )

                # Check if drive_result contains an error
                if "Error:" in drive_result or "not installed" in drive_result.lower():
                    error_msg = f"Failed to create Excel on Google Drive: {drive_result}"
                    await event_queue.put({"event": "error", "data": error_msg})
                    return

                # Extract Drive link from result
                if "Link:" in drive_result:
                    drive_link = drive_result.split("Link:")[-1].strip()
                elif "https://drive.google.com" in drive_result:
                    urls = re.findall(r"https://drive\.google\.com[^\s]+", drive_result)
                    drive_link = urls[0] if urls else drive_result
                else:
                    error_msg = f"Could not extract Drive link from result: {drive_result}"
                    await event_queue.put({"event": "error", "data": error_msg})
                    return

                await event_queue.put({
                    "event": "status",
                    "data": f"Step 1 complete! Drive link: {drive_link}"
                })

                # Step 2: Send email with Drive link
                await event_queue.put({
                    "event": "status",
                    "data": "Step 2: Sending email with Drive link..."
                })
                
                # Create email subject with user query
                subject_query = email_subject_query[:100] if len(email_subject_query) > 100 else email_subject_query
                email_subject = f"Results for your query: {subject_query}"
                
                email_result = await gmail_send_with_drive_link(
                    to_email=email,
                    subject=email_subject,
                    drive_link=drive_link,
                    ctx=ctx,
                    body_text=f"The table has been extracted from {url} and saved to Google Drive.",
                    credentials_path=credentials_path,
                )

                # Check if email sending failed
                if "Error:" in email_result or "not installed" in email_result.lower():
                    error_msg = f"Failed to send email: {email_result}"
                    await event_queue.put({
                        "event": "warning",
                        "data": f"Excel file created, but email failed: {error_msg}"
                    })
                    await event_queue.put({
                        "event": "complete",
                        "data": f"Excel file created on Google Drive. Drive link: {drive_link}. Email failed: {email_result}"
                    })
                else:
                    await event_queue.put({
                        "event": "status",
                        "data": f"Step 2 complete! Email sent to {email}"
                    })
                    await event_queue.put({
                        "event": "complete",
                        "data": f"✅ Workflow completed successfully! Excel file created and email sent. Drive link: {drive_link}"
                    })

            except Exception as e:
                error_msg = f"Error in workflow: {str(e)}"
                await event_queue.put({"event": "error", "data": error_msg})
                traceback.print_exc(file=sys.stderr)

        # Start SSE server
        app = web.Application()
        app.router.add_get("/events", sse_handler)

        # Start server in background
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", sse_port)
        await site.start()

        await ctx.info(f"SSE server started at {sse_url}")

        # Run workflow in background
        workflow_task = asyncio.create_task(run_workflow_with_sse())

        # Wait for workflow to complete
        await workflow_task

        # Keep server running briefly to allow client to receive final event
        await asyncio.sleep(2)

        await runner.cleanup()

        return f"SSE streaming completed. Endpoint was: {sse_url}. Connect to this URL to receive real-time progress updates."

    except Exception as e:
        error_msg = f"Error in SSE workflow: {str(e)}"
        await ctx.error(error_msg)
        traceback.print_exc(file=sys.stderr)
        return f"Error: {error_msg}"


if __name__ == "__main__":
    print("mcp_server_4.py starting")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")  # Run with stdio for direct execution
        print("\nShutting down...")

