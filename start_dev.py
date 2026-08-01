#!/usr/bin/env python3
"""
Ask-N-Seek Development Launcher
Starts all three services for local development:
  1. FastAPI Bridge  (port 8000)
  2. Next.js Frontend (port 3000)

Usage:
  python start_dev.py
"""
import subprocess
import sys
import os
import time
import platform

REPO_ROOT    = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")
BRIDGE_DIR   = os.path.join(FRONTEND_DIR, "bridge")


def run_in_terminal(title: str, cwd: str, cmd: str) -> None:
    """Open a new terminal window and run cmd in it (keeps the window open)."""
    system = platform.system()
    if system == "Windows":
        # cmd /k keeps window open after the command exits
        full = f'start "{title}" cmd /k "cd /d {cwd} && {cmd}"'
        subprocess.Popen(full, shell=True)
    elif system == "Darwin":
        script = f'tell app "Terminal" to do script "cd {cwd} && {cmd}"'
        subprocess.Popen(["osascript", "-e", script])
    else:  # Linux (gnome-terminal or xterm fallback)
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
    """Warn about missing tools but don't abort — user may have them on PATH."""
    ok = True
    for tool in ["uvicorn", "npm"]:
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
    print("  Ask-N-Seek  |  Development Launcher")
    print("=" * 60)

    print("\n[prereq] Checking tools...")
    check_prereqs()

    # ── 1. FastAPI Bridge ─────────────────────────────────────────────────
    print("\n[1/2] Starting FastAPI Bridge on port 8000 ...")
    bridge_cmd = f"{sys.executable} -m uvicorn main:app --reload --port 8000"
    run_in_terminal("ANS  Bridge :8000", BRIDGE_DIR, bridge_cmd)
    time.sleep(2)

    # ── 2. Next.js Frontend ───────────────────────────────────────────────
    print("[2/2] Starting Next.js Frontend on port 3000 ...")
    frontend_cmd = "npm run dev"
    run_in_terminal("ANS  Frontend :3000", FRONTEND_DIR, frontend_cmd)
    time.sleep(1)

    print("\n" + "=" * 60)
    print("  Services starting in separate terminals.")
    print()
    print("  Bridge   →  http://localhost:8000")
    print("  Frontend →  http://localhost:3000")
    print()
    print("  Quick test:  http://localhost:8000/scenarios")
    print("               http://localhost:8000/health")
    print("=" * 60)


if __name__ == "__main__":
    main()
