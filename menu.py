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
from switch_manager import SwitchManagerPanel  # type: ignore

PANEL_CLASS = 'SwitchManagerPanel'
PANEL_NAME = 'Switch Manager'
NEW_PANEL_ID = 'uk.co.bcn.multishot.switch_manager'
LEGACY_PANEL_ID = 'uk.co.bcn.multishot.screens_manager'


def add_switch_manager_panel() -> Optional[object]:
    """Create and dock the Switch Manager panel next to Properties."""

    try:
        pane = nuke.getPaneFor('Properties.1')
        registered = panels.registerWidgetAsPanel(
            PANEL_CLASS,
            PANEL_NAME,
            NEW_PANEL_ID,
            True,
        )
        return registered.addToPane(pane) if pane else registered
    except Exception:
        return None


# GUI-only wiring
try:
    if nuke.env['gui']:
        # Pane menu entry
        nuke.menu('Pane').addCommand(PANEL_NAME, add_switch_manager_panel)
        # Enable layout save/restore
        nukescripts.registerPanel(NEW_PANEL_ID, add_switch_manager_panel)
        # Legacy ID for saved layouts created before the rename
        nukescripts.registerPanel(LEGACY_PANEL_ID, add_switch_manager_panel)
        # Optional: Nuke menu shortcut
        nuke.menu('Nuke').addCommand(
            f'BCN Multishot/{PANEL_NAME}',
            add_switch_manager_panel,
        )
except Exception:
    pass
