"""Compatibility shim for legacy imports of `screens_manager`.

Switch Manager now lives in `nuke_tools.switch_manager`. This module proxies to
the new implementation so existing scripts that still import
`screens_manager.ScreensManagerPanel` continue to work.
"""
from __future__ import annotations

try:
    from .switch_manager import SwitchManagerPanel, set_default_screen_via_ui  # type: ignore
except Exception:  # pragma: no cover - fallback when package-relative import fails
    from switch_manager import SwitchManagerPanel, set_default_screen_via_ui  # type: ignore

# Backwards-compatible alias for old callers
ScreensManagerPanel = SwitchManagerPanel

__all__ = ["ScreensManagerPanel", "SwitchManagerPanel", "set_default_screen_via_ui"]

 