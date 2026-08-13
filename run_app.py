#!/usr/bin/env python3
"""
AI Learning Assistant Application Launcher
Runs FastAPI web server and opens the browser interface.
"""

import sys
import os
import time
import webbrowser
import threading
import uvicorn

def open_browser(url: str, delay: float = 1.5):
    """Open web browser after a short startup delay."""
    time.sleep(delay)
    print(f"🚀 Opening AI Learning Assistant in your browser: {url}")
    webbrowser.open(url)

def main():
    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}"

    print("\n=======================================================")
    print("🎓  AI LEARNING ASSISTANT WEB APPLICATION")
    print("=======================================================")
    print(f"🌐 App URL:  {url}")
    print(f"📁 Root Dir: {os.path.abspath('.')}")
    print("=======================================================\n")

    # Launch browser thread
    threading.Thread(target=open_browser, args=(url, 1.5), daemon=True).start()

    # Run uvicorn server
    uvicorn.run("backend.app:app", host=host, port=port, reload=True)

if __name__ == "__main__":
    main()
