"""
Centralized resources path manager and utils.
"""

from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """
    Return the absolute path to an application resource.

    Works both during normal Python execution and inside
    a PyInstaller bundle.
    """
    app_dir = Path(__file__).resolve().parent.parent
    return app_dir / relative_path