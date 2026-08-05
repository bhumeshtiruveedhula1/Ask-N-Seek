#!/usr/bin/env python3
"""
Ask-N-Seek Development Launcher v2.5
Runs bridge + static server in THIS terminal (no new windows).
Logs go to bridge.log and static.log in the project root.

Usage:
    python start_dev.py

Stop with Ctrl+C.
"""
import subprocess
import sys
import os
import time

REPO_ROOT    = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")
BRIDGE_LOG   = os.path.join(REPO_ROOT, "bridge.log")
STATIC_LOG   = os.path.join(REPO_ROOT, "static.log")


def main() -> None:
    print("=" * 60)
    print("  Ask-N-Seek v2.5  |  Development Launcher")
    print("=" * 60)

    # ── 1. FastAPI Bridge ────────────────────────────────────────
    # Run from REPO_ROOT so all engine imports resolve correctly.
    bridge_cmd = [
        sys.executable, "-m", "uvicorn",
        "frontend.bridge_server:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload",
    ]
    print(f"\n[1/2] Starting Bridge → http://127.0.0.1:8000")
    print(f"      Logs: {BRIDGE_LOG}")
    bridge_log_fh = open(BRIDGE_LOG, "w", buffering=1)
    bridge = subprocess.Popen(
        bridge_cmd,
        cwd=REPO_ROOT,           # critical: must be repo root for imports
        stdout=bridge_log_fh,
        stderr=subprocess.STDOUT,
    )
    print(f"      PID: {bridge.pid}")

    # ── 2. Static file server ────────────────────────────────────
    static_cmd = [
        sys.executable, "-m", "http.server",
        "3000", "--bind", "127.0.0.1",
    ]
    print(f"\n[2/2] Starting Frontend → http://127.0.0.1:3000")
    print(f"      Logs: {STATIC_LOG}")
    static_log_fh = open(STATIC_LOG, "w", buffering=1)
    static = subprocess.Popen(
        static_cmd,
        cwd=FRONTEND_DIR,
        stdout=static_log_fh,
        stderr=subprocess.STDOUT,
    )
    print(f"      PID: {static.pid}")

    # ── Wait for bridge to be ready ──────────────────────────────
    print("\n  Waiting for bridge to be ready", end="", flush=True)
    ready = False
    for _ in range(20):
        time.sleep(0.5)
        print(".", end="", flush=True)
        # Check process is still alive
        if bridge.poll() is not None:
            print("\n\n  ❌ Bridge died immediately! Check bridge.log:")
            with open(BRIDGE_LOG) as f:
                print(f.read()[-2000:])
            static.terminate()
            sys.exit(1)
        # Try health check
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
            ready = True
            break
        except Exception:
            pass
    print()

    if not ready:
        print("  ⚠️  Bridge health check timed out — check bridge.log")
    else:
        print("  ✅ Bridge is healthy")

    print()
    print("=" * 60)
    print("  Open → http://127.0.0.1:3000/index.html")
    print()
    print("  Bridge   → http://127.0.0.1:8000")
    print("  API Docs → http://127.0.0.1:8000/docs")
    print()
    print("  Quick test:")
    print("    curl http://127.0.0.1:8000/health")
    print()
    print("  Press Ctrl+C to stop both servers.")
    print("=" * 60)

    # ── Monitor loop ─────────────────────────────────────────────
    try:
        while True:
            time.sleep(2)
            if bridge.poll() is not None:
                print("\n  ❌ Bridge server died! Last 50 lines of bridge.log:")
                with open(BRIDGE_LOG) as f:
                    lines = f.readlines()
                print("".join(lines[-50:]))
                print("  Restart with: python start_dev.py")
                break
            if static.poll() is not None:
                print("\n  ❌ Static server died! Check static.log")
                break
    except KeyboardInterrupt:
        print("\n\n  Shutting down...")
    finally:
        bridge.terminate()
        static.terminate()
        bridge_log_fh.close()
        static_log_fh.close()
        print("  Done.")


if __name__ == "__main__":
    main()
