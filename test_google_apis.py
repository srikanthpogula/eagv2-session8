"""
Quick test script to verify Google APIs are available in mcp_server_4.py
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from mcp_server_4 import GOOGLE_APIS_AVAILABLE
    
    if GOOGLE_APIS_AVAILABLE:
        print("✅ Google APIs are available!")
        print("✅ mcp_server_4.py can import Google API packages")
        print("\nYou can now restart your agent and the tools should work.")
    else:
        print("❌ Google APIs are NOT available")
        print("Please install: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)
        
except ImportError as e:
    print(f"❌ Error importing mcp_server_4: {e}")
    sys.exit(1)

