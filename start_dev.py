#!/usr/bin/env python3
"""
Ask-N-Seek Development Launcher v2.4
Starts both services for local development:
  1. FastAPI Bridge  (port 8000) — fresh_clone/frontend/bridge_server.py
  2. Static HTML Server (port 3000) — serves fresh_clone/frontend/

Usage:
  python start_dev.py
"""
import subprocess
import sys
import os
import time
import platform

REPO_ROOT     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR  = os.path.join(REPO_ROOT, "frontend")


def run_in_terminal(title: str, cwd: str, cmd: str) -> None:
    """Open a new terminal window and run cmd in it (keeps the window open)."""
    system = platform.system()
    if system == "Windows":
        full = f'start "{title}" cmd /k "cd /d {cwd} && {cmd}"'
        subprocess.Popen(full, shell=True)
    elif system == "Darwin":
        script = f'tell app "Terminal" to do script "cd {cwd} && {cmd}"'
        subprocess.Popen(["osascript", "-e", script])
    else:  # Linux
        try:
            subprocess.Popen(
                ["gnome-terminal", "--title", title, "--", "bash", "-c",
                 f"cd {cwd} && {cmd}; exec bash"]
            )
        except FileNotFoundError:
            subprocess.Popen(
                ["xterm", "-T", title, "-e",
                 f"bash -c 'cd {cwd} && {cmd}; bash'"]
            )


def check_prereqs() -> bool:
    """Warn about missing tools but don't abort."""
    ok = True
    tools = ["uvicorn"] if platform.system() == "Windows" else ["uvicorn"]
    for tool in tools:
        result = subprocess.run(
            f"where {tool}" if platform.system() == "Windows" else f"which {tool}",
            shell=True, capture_output=True
        )
        if result.returncode != 0:
            print(f"  [WARN] '{tool}' not found on PATH — install it first.")
            ok = False
    return ok


def main() -> None:
    print("=" * 60)
    print("  Ask-N-Seek v2.4  |  Development Launcher")
    print("=" * 60)

    print("\n[prereq] Checking tools...")
    check_prereqs()

    # ── 1. FastAPI Bridge (bridge_server.py) ─────────────────────────────────
    print("\n[1/2] Starting FastAPI Bridge on port 8000 ...")
    # Launch uvicorn directly against bridge_server.py in frontend/ dir
    bridge_cmd = f"{sys.executable} -m uvicorn bridge_server:app --reload --port 8000 --host 0.0.0.0"
    run_in_terminal("ANS  Bridge :8000", FRONTEND_DIR, bridge_cmd)
    time.sleep(2)

    # ── 2. Static file server for the HTML frontend ───────────────────────────
    print("[2/2] Starting HTML Static Server on port 3000 ...")
    # Use Python's built-in http.server for zero-dependency static serving
    static_cmd = f"{sys.executable} -m http.server 3000 --bind 127.0.0.1"
    run_in_terminal("ANS  Frontend :3000", FRONTEND_DIR, static_cmd)
    time.sleep(1)

    print("\n" + "=" * 60)
    print("  Services starting in separate terminals.")
    print()
    print("  Bridge    →  http://localhost:8000")
    print("  Frontend  →  http://localhost:3000")
    print("  Docs      →  http://localhost:8000/docs")
    print()
    print("  Quick test:")
    print("    curl http://localhost:8000/health")
    print("    curl http://localhost:8000/scenarios")
    print()
    print("  Open  http://localhost:3000/index.html  in your browser.")
    print("=" * 60)


if __name__ == "__main__":
    main()
