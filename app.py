"""
app.py — Entry point for Odysseus Part 3.

Usage:
    python app.py

Launches the Gradio interface on http://localhost:7860
"""

from __future__ import annotations

import logging
import sys
import os

# Make engine/ and ui/ importable regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import GRADIO_HOST, GRADIO_PORT
from engine.stub_data import count_stub_rows
from ui.gradio_app import build_app, CUSTOM_CSS, SETUP_JS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("odysseus.app")


def main() -> None:
    logger.info("Odysseus Part 3 — starting up.")
    logger.info("Stub collection: %d detection rows across 3 videos.", count_stub_rows())
    logger.info("Launching Gradio on http://%s:%d", GRADIO_HOST, GRADIO_PORT)

    demo = build_app()
    demo.launch(
        server_name=GRADIO_HOST,
        server_port=GRADIO_PORT,
        share=False,
        show_error=True,
        css=CUSTOM_CSS,
        js=SETUP_JS,
    )


if __name__ == "__main__":
    main()
