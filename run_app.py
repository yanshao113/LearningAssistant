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

CONDA_PYTHON = "/Users/shaoyan/opt/anaconda3/envs/writing_assistant/bin/python3"
try:
    import uvicorn
except ImportError:
    if os.path.exists(CONDA_PYTHON) and sys.executable != CONDA_PYTHON:
        os.execv(CONDA_PYTHON, [CONDA_PYTHON] + sys.argv)
    else:
        raise


import socket
import subprocess

def clear_port_if_occupied(port: int = 8000):
    """Clean up stale processes listening on the target port if any."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) == 0:
                print(f"⚠️ Port {port} is occupied by an old process. Cleaning up...")
                res = subprocess.run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True)
                pids = res.stdout.strip().split()
                for pid in pids:
                    if pid and int(pid) != os.getpid():
                        try:
                            subprocess.run(["kill", "-9", pid], check=False)
                        except Exception:
                            pass
                time.sleep(0.5)
    except Exception as e:
        print(f"Port check warning: {e}")

def open_browser(url: str, delay: float = 1.5):
    """Open web browser after a short startup delay."""
    time.sleep(delay)
    print(f"🚀 Opening AI Learning Assistant in your browser: {url}")
    webbrowser.open(url)

def main():
    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}"

    clear_port_if_occupied(port)

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
