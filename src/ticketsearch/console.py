"""Configuracion de consola para Windows (UTF-8) y silencio de logs ruidosos."""

from __future__ import annotations

import logging
import os
import sys
import warnings

from rich.console import Console


def setup_console() -> Console:
    # PowerShell clasico usa cp1252/cp850: forzamos UTF-8 para tildes y enies
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    warnings.filterwarnings("ignore")
    for name in ("presidio-analyzer", "presidio-anonymizer", "chromadb", "httpx"):
        logging.getLogger(name).setLevel(logging.ERROR)
    return Console(highlight=False)
