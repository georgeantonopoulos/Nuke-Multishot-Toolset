"""BCN Multishot menu bootstrap.

Minimal, Deadline-style: add plugin paths, then in GUI add a Pane command
and a callable that docks the panel.
"""

from typing import Optional

import nuke  # type: ignore
import nukescripts  # type: ignore
from nukescripts import panels  # type: ignore


nuke.pluginAddPath('./nuke_tools')

# Tools on NUKE_PATH
from screens_manager import ScreensManagerPanel  # type: ignore
from render_hooks import encapsulate_write_with_variable_group  # type: ignore


def add_screens_manager_panel() -> Optional[object]:
    """Create and dock the Screens Manager panel next to Properties."""

    try:
        pane = nuke.getPaneFor('Properties.1')
        return panels.registerWidgetAsPanel('ScreensManagerPanel', 'Screens Manager', 'uk.co.bcn.multishot.screens_manager', True).addToPane(pane) if pane else panels.registerWidgetAsPanel('ScreensManagerPanel', 'Screens Manager', 'uk.co.bcn.multishot.screens_manager', True)
    except Exception:
        return None


# GUI-only wiring
try:
    if nuke.env['gui']:
        # Pane menu entry
        nuke.menu('Pane').addCommand('Screens Manager', add_screens_manager_panel)
        # Enable layout save/restore
        nukescripts.registerPanel('uk.co.bcn.multishot.screens_manager', add_screens_manager_panel)
        # Optional: Nuke menu shortcut
        nuke.menu('Nuke').addCommand(
            'BCN Multishot/Screens Manager',
            add_screens_manager_panel,
        )
        # Write helpers
        nuke.menu('Nuke').addCommand(
            'BCN Multishot/Wrap Node in Variable Group',
            encapsulate_write_with_variable_group,
        )
except Exception:
    pass
