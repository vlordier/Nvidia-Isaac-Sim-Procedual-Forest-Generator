"""
UE5 integration package for genesis_forest.

Two modules for the two-side architecture:
- ue5_server.py  — runs INSIDE UE5 (Python console)
- client.py      — runs in Gradio/Python backend (outside UE5)
"""

from ue5.client import (
    UE5RenderClient,
    RenderParams,
    render_in_ue5,
    check_ue5_status,
    DEFAULT_PORT,
)

__all__ = [
    "UE5RenderClient",
    "RenderParams",
    "render_in_ue5",
    "check_ue5_status",
    "DEFAULT_PORT",
]
