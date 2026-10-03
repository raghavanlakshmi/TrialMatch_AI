"""Streamlit Community Cloud entry point: replay-mode demo with lightweight dependencies.

Set the app's main file to deploy/streamlit_app.py. Community Cloud reads
deploy/requirements.txt, which omits the heavy retrieval stack that only live
runs need.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402

app.main()
