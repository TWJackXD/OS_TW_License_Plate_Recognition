#!/usr/bin/env python3
"""Start the violation reporting web app."""

import os

# Load .env before importing web (which imports recognize_plate defaults).
from recognize_plate import load_dotenv  # noqa: E402

load_dotenv()

from web.app import app  # noqa: E402
import uvicorn

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8010"))
    uvicorn.run(app, host=host, port=port)
