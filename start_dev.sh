#!/usr/bin/env bash
# Ask-N-Seek development launcher (Unix wrapper)
set -e
cd "$(dirname "$0")"
python3 start_dev.py "$@"
