#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python setup_local.py
.venv/bin/python run.py
