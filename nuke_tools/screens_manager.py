"""Screens Manager panel for Nuke 16 multishot workflows.

Provides a minimal dockable Qt panel to:
- maintain `__default__.screens` list options
- ensure per-screen Variable Sets exist at root
- create per-screen VariableGroups (optional scopes)
- optionally create a `VariableSwitch` preview node

This keeps to expressions/VariableSwitch/Link nodes and avoids generic
callbacks; when a callback is required, prefer `nuke.callbacks.onGsvSetChanged`.
"""

from typing import List, Optional, Sequence
import os

try:
    import nuke  # type: ignore
except Exception:  # pragma: no cover
    nuke = None  # type: ignore

# Try PySide6 first, then alternate import style, then PySide2.
try:  # PySide6 (module subpackage style)
    import PySide6.QtCore as QtCore  # type: ignore
    import PySide6.QtWidgets as QtWidgets  # type: ignore
    import PySide6.QtGui as QtGui  # type: ignore
except Exception:  # pragma: no cover
    try:  # PySide6 (from package style)
        from PySide6 import QtCore as QtCore  # type: ignore
        from PySide6 import QtWidgets as QtWidgets  # type: ignore
        from PySide6 import QtGui as QtGui  # type: ignore
    except Exception:
        try:  # PySide2 fallback
            import PySide2.QtCore as QtCore  # type: ignore
            import PySide2.QtWidgets as QtWidgets  # type: ignore
            import PySide2.QtGui as QtGui  # type: ignore
        except Exception:
            QtCore = None  # type: ignore
            QtWidgets = None  # type: ignore
            QtGui = None  # type: ignore

import gsv_utils

try:
    from . import render_hooks  # type: ignore
except Exception:  # pragma: no cover
    try:
        import render_hooks  # type: ignore
    except Exception:  # pragma: no cover
        render_hooks = None  # type: ignore


if QtWidgets is None:
    class ScreensManagerPanel(object):  # type: ignore[misc]
        """Placeholder when Qt is unavailable.

        Instantiation raises a clear error so the module can import cleanly in
        any environment, and the failure is deferred to creation time.
        """

        def __init__(self, *args, **kwargs) -> None:  # noqa: D401
            raise RuntimeError(
                "PySide QtWidgets is not available. Cannot create ScreensManagerPanel."
            )
else:
    class ScreensManagerPanel(QtWidgets.QWidget):  # type: ignore[misc]
        """Simple UI for managing screens.

        The UI is intentionally minimal:
          - A line edit to enter comma-separated screen names
          - A default screen combobox
          - Buttons to apply/update, build VariableGroups, and create VariableSwitch
        """

        # Singleton-style handle so other modules can poke the UI when needed
        instance: Optional["ScreensManagerPanel"] = None

        def __init__(self, parent=None) -> None:  # noqa: D401
            super().__init__(parent)
            self.setWindowTitle("Screens Manager")
            self.setObjectName("ScreensManagerPanel")
            ScreensManagerPanel.instance = self
            self._build_ui()
            self._load_from_gsv()
            self._install_gsv_callback()
            
        def _build_ui(self) -> None:
            """Build and wire an artist-friendly Qt UI."""
            self.setMinimumWidth(420)
            root_layout = QtWidgets.QVBoxLayout(self)
            root_layout.setContentsMargins(12, 12, 12, 12)
            root_layout.setSpacing(10)

            header = self._build_header()
            root_layout.addWidget(header)

            hero_copy = QtWidgets.QLabel(
                "Create variations, generate switches, lock Outputs to selected Option."
            )
            hero_copy.setWordWrap(True)
            hero_copy.setStyleSheet("color: #d6d6d6; font-size: 11px;")
            root_layout.addWidget(hero_copy)

            # Screen configuration group
            form_group = QtWidgets.QGroupBox("Screen Setup")
            form_group.setObjectName("sm_setup_group")
            form_group_layout = QtWidgets.QVBoxLayout(form_group)
            form_group_layout.setContentsMargins(10, 10, 10, 10)

            form = QtWidgets.QFormLayout()
            form.setLabelAlignment(QtCore.Qt.AlignRight)

            self.screens_edit = QtWidgets.QLineEdit(self)
            self.screens_edit.setPlaceholderText("Comma-separated screen names, e.g. Moxy,Godzilla,NYD400")
            self.screens_edit.setToolTip("Enter a list of screen names. Duplicates will be removed.")
            form.addRow("Screens:", self.screens_edit)

            self.default_combo = QtWidgets.QComboBox(self)
            self.default_combo.setObjectName("sm_default_screen")
            self.default_combo.setToolTip("Pick the default/current screen (writes also use this unless assigned).")
            form.addRow("Current Selection:", self.default_combo)
            form_group_layout.addLayout(form)

            self.screen_summary = QtWidgets.QLabel("No screens configured.")
            self.screen_summary.setObjectName("sm_screen_summary")
            self.screen_summary.setStyleSheet("color: #9ad8ff; font-style: italic;")
            form_group_layout.addWidget(self.screen_summary)

            chip_container = QtWidgets.QWidget(self)
            self.screen_chip_layout = QtWidgets.QHBoxLayout(chip_container)
            self.screen_chip_layout.setContentsMargins(0, 0, 0, 0)
            self.screen_chip_layout.setSpacing(6)
            form_group_layout.addWidget(chip_container)

            root_layout.addWidget(form_group)

            # Action buttons arranged in a grid for quicker scanning
            actions_group = QtWidgets.QGroupBox("Quick Actions")
            actions_group.setObjectName("sm_actions_group")
            actions_layout = QtWidgets.QGridLayout(actions_group)
            actions_layout.setHorizontalSpacing(8)
            actions_layout.setVerticalSpacing(8)

            self.apply_btn = QtWidgets.QPushButton("Sync Screens to GSV", self)
            self.groups_btn = QtWidgets.QPushButton("Build VariableGroups", self)
            self.switch_btn = QtWidgets.QPushButton("Create VariableSwitch", self)
            self.wrap_btn = QtWidgets.QPushButton("Lock Write node to Option", self)

            self.apply_btn.setToolTip("Create/update the global screens list and default value. Also ensures screen sets.")
            self.groups_btn.setToolTip("Create a VariableGroup per screen (screen_<name>) if missing.")
            self.switch_btn.setToolTip("Create a VariableSwitch named 'ScreenSwitch' and inputs for every screen.")
            self.wrap_btn.setToolTip("Insert a VariableGroup upstream of the selected Write or publishable Group, wiring it to the current screen.")

            self._style_action_button(self.apply_btn, role="primary")
            self._style_action_button(self.groups_btn, role="secondary")
            self._style_action_button(self.switch_btn, role="secondary")
            self._style_action_button(self.wrap_btn, role="accent")

            actions_layout.addWidget(self.apply_btn, 0, 0)
            actions_layout.addWidget(self.groups_btn, 0, 1)
            actions_layout.addWidget(self.switch_btn, 1, 0)
            actions_layout.addWidget(self.wrap_btn, 1, 1)

            root_layout.addWidget(actions_group)
            root_layout.addStretch(1)

            # Wire signals
            self.apply_btn.clicked.connect(self._on_apply)
            self.groups_btn.clicked.connect(self._on_groups)
            self.switch_btn.clicked.connect(self._on_switch)
            self.wrap_btn.clicked.connect(self._on_wrap)
            self.default_combo.currentTextChanged.connect(self._on_default_changed)

        def _build_header(self) -> QtWidgets.QWidget:
            """Create a branded header with logo + text."""
            header = QtWidgets.QFrame(self)
            header.setObjectName("sm_header")
            header.setStyleSheet(
                """
                QFrame#sm_header {
                    background-color: #20232a;
                    border: 1px solid #2f3847;
                    border-radius: 8px;
                }
                """
            )
            layout = QtWidgets.QHBoxLayout(header)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            self.logo_label = QtWidgets.QLabel(header)
            self.logo_label.setAlignment(QtCore.Qt.AlignCenter)
            self.logo_label.setObjectName("switchManagerLogo")
            self.logo_label.setMinimumSize(72, 72)
            self.logo_label.setMaximumHeight(128)
            self._install_logo_pixmap()
            layout.addWidget(self.logo_label, 0)

            title_block = QtWidgets.QVBoxLayout()
            title = QtWidgets.QLabel("Screens Manager", header)
            title.setStyleSheet("font-size: 16px; font-weight: 600; color: #f2f2f2;")
            subtitle = QtWidgets.QLabel("VariableSwitch + VariableGroup command center", header)
            subtitle.setStyleSheet("color: #8fb6ff; font-size: 12px;")
            subtitle.setWordWrap(True)
            title_block.addWidget(title)
            title_block.addWidget(subtitle)
            title_block.addStretch(1)
            layout.addLayout(title_block, 1)
            return header

        def _style_action_button(self, button: QtWidgets.QPushButton, role: str = "secondary") -> None:
            """Give each action button a consistent style."""
            palette = {
                "primary": ("#2f7bf2", "#2462c1"),
                "accent": ("#a68a00", "#2f7c55"),
                "secondary": ("#3a3f4b", "#2b2f38"),
            }
            normal, pressed = palette.get(role, palette["secondary"])
            button.setMinimumHeight(44)
            button.setCheckable(False)
            button.setProperty("smRole", role)
            if QtGui is not None:
                button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            button.setStyleSheet(
                f"""
                QPushButton[smRole="{role}"] {{
                    background-color: {normal};
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 6px;
                    padding: 6px 10px;
                    color: #f5f5f5;
                    font-weight: 500;
                }}
                QPushButton[smRole="{role}"]:hover {{
                    border-color: rgba(255,255,255,0.2);
                }}
                QPushButton[smRole="{role}"]:pressed {{
                    background-color: {pressed};
                }}
                """
            )
            if role == "primary":
                button.setDefault(True)

        def _update_screen_summary(self, screens: Sequence[str]) -> None:
            """Refresh helper text + pills for the current screen list."""
            if not hasattr(self, "screen_summary"):
                return
            count = len(screens)
            if count == 0:
                summary = "No screens configured yet."
            elif count == 1:
                summary = f"1 screen active: {screens[0]}"
            elif count <= 4:
                summary = f"{count} screens ready • {', '.join(screens)}"
            else:
                summary = f"{count} screens ready • {', '.join(screens[:3])}…"
            self.screen_summary.setText(summary)
            self._render_screen_chips(screens)

        def _render_screen_chips(self, screens: Sequence[str]) -> None:
            """Show pill labels for each screen for quick scanning."""
            layout = getattr(self, "screen_chip_layout", None)
            if layout is None:
                return
            self._clear_layout(layout)
            if not screens:
                placeholder = QtWidgets.QLabel("Add screens to preview them here.")
                placeholder.setStyleSheet("color: #6c788d;")
                layout.addWidget(placeholder)
                layout.addStretch(1)
                return
            for name in screens:
                chip = QtWidgets.QLabel(name)
                chip.setStyleSheet(
                    """
                    background-color: #2f3542;
                    border-radius: 10px;
                    padding: 4px 10px;
                    color: #f0f6ff;
                """
                )
                layout.addWidget(chip)
            layout.addStretch(1)

        def _clear_layout(self, layout: QtWidgets.QLayout) -> None:
            """Remove all widgets/items from the provided layout."""
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                    continue
                child_layout = item.layout()
                if child_layout is not None:
                    self._clear_layout(child_layout)

        def set_default_screen(self, name: str, allow_add: bool = True, emit_signal: bool = True) -> None:
            """Programmatically set the Default screen combobox.

            If the provided name does not exist and `allow_add` is True, it will
            be appended to the combo items. When `emit_signal` is True the
            combobox's signals are left enabled so downstream handlers (which
            sync the GSV) will execute.
            """
            combo = self.default_combo
            if combo is None:
                return
            # Find current index
            idx = combo.findText(name, QtCore.Qt.MatchFixedString) if name else -1
            if idx < 0 and allow_add and name:
                try:
                    combo.addItem(name)
                    idx = combo.findText(name, QtCore.Qt.MatchFixedString)
                except Exception:
                    pass
            try:
                if not emit_signal:
                    combo.blockSignals(True)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                elif name:
                    combo.setCurrentText(name)
            finally:
                if not emit_signal:
                    combo.blockSignals(False)

        def _install_logo_pixmap(self) -> None:
            """Load and set the banner logo pixmap if available.

            The image is expected at project root as `switch_manager_logo.png`.
            This is a best-effort enhancement; failures are silently ignored.
            """
            if QtGui is None:
                return
            try:
                # Resolve to repo root where the PNG lives
                this_dir = os.path.dirname(os.path.abspath(__file__))
                root_dir = os.path.dirname(this_dir)
                logo_candidates = [
                    os.path.join(root_dir, "switch_manager_logo_alpha.png")
                ]
                logo_path = next((p for p in logo_candidates if os.path.exists(p)), None)
                if logo_path is None:
                    return
                self._logo_pixmap = QtGui.QPixmap(logo_path)
                if not self._logo_pixmap.isNull():
                    scaled = self._logo_pixmap.scaledToHeight(
                        96, QtCore.Qt.SmoothTransformation
                    )
                    self.logo_label.setPixmap(scaled)
            except Exception:
                # Non-fatal; simply omit the logo
                pass

        def resizeEvent(self, event):  # type: ignore[override]
            """Keep the logo nicely scaled on resize."""
            try:
                if QtGui is not None and hasattr(self, "_logo_pixmap") and not self._logo_pixmap.isNull():
                    max_height = max(72, min(128, int(self.height() * 0.18)))
                    scaled = self._logo_pixmap.scaledToHeight(
                        max_height, QtCore.Qt.SmoothTransformation
                    )
                    self.logo_label.setPixmap(scaled)
            except Exception:
                pass
            super().resizeEvent(event)

        def _load_from_gsv(self) -> None:
            """Populate UI from the current `__default__.screens` options."""
            options = gsv_utils.get_list_options("__default__.screens")
            self._set_combo_items(self.default_combo, options)
            # Set combo to current selection without emitting change
            current = gsv_utils.get_value("__default__.screens")
            if current:
                try:
                    self.default_combo.blockSignals(True)
                    idx = self.default_combo.findText(current)
                    if idx >= 0:
                        self.default_combo.setCurrentIndex(idx)
                finally:
                    self.default_combo.blockSignals(False)
            if options:
                self.screens_edit.setText(
                    ",".join(options)
                )
            self._update_screen_summary(options)

        def _install_gsv_callback(self) -> None:
            """Install a GSV change callback to keep UI synced with globals.

            Uses `nuke.callbacks.onGsvSetChanged` when available. The handler is
            resilient to signature differences across Nuke versions and simply
            reloads the combobox/text from the root GSV when any change occurs.
            """

            if nuke is None:
                return
            try:
                cb_mod = getattr(nuke, "callbacks", None)
                if cb_mod and hasattr(cb_mod, "onGsvSetChanged"):
                    # Register once per widget instance
                    def _handler(*_args, **_kwargs):  # noqa: D401
                        try:
                            self._load_from_gsv()
                        except Exception:
                            pass

                    cb_mod.onGsvSetChanged(_handler)
            except Exception:
                # Best-effort; UI will still work via direct combobox edits
                pass

        def _set_combo_items(self, combo: QtWidgets.QComboBox, items: Sequence[str]) -> None:
            """Replace all items in a combobox (signals blocked during update)."""
            try:
                combo.blockSignals(True)
                combo.clear()
                for item in items:
                    combo.addItem(item)
            finally:
                combo.blockSignals(False)

        def _parse_screens(self) -> List[str]:
            """Parse and de-duplicate comma-separated screen names from the edit."""
            text = self.screens_edit.text().strip()
            if not text:
                return []
            names = [n.strip() for n in text.split(",")]
            # de-duplicate while preserving order
            seen = set()
            unique: List[str] = []
            for n in names:
                if n and n not in seen:
                    unique.append(n)
                    seen.add(n)
            return unique

        # Actions
        def _on_apply(self) -> None:
            """Apply screens/default to GSV and refresh UI."""
            screens = self._parse_screens()
            if not screens:
                return
            default = self.default_combo.currentText() or screens[0]
            gsv_utils.ensure_screen_list(screens, default)
            # Also ensure each screen has a Set at the root for %Set.Var usage
            gsv_utils.ensure_screen_sets(screens)
            # Proactively ensure a VariableGroup per screen so artists see a
            # dedicated scope folder after adding new screens.
            try:
                for name in screens:
                    gsv_utils.create_variable_group(f"screen_{name}")
            except Exception:
                pass
            self._load_from_gsv()

        def _on_groups(self) -> None:
            """Ensure VariableGroup nodes exist for each screen name."""
            for name in self._parse_screens():
                grp = gsv_utils.create_variable_group(f"screen_{name}")
                # Lock the group's local scope to this option so it evaluates correctly
                try:
                    if grp is not None:
                        grp["gsv"].setGsvValue("__default__.screens", str(name))
                except Exception:
                    pass

        def _on_switch(self) -> None:
            """Create a `VariableSwitch` wired to `__default__.screens`."""

            if nuke is None:
                return

            screens = gsv_utils.get_list_options("__default__.screens")
            if not screens:
                screens = self._parse_screens()
            if not screens:
                self._warn_user("Add at least one screen before creating a VariableSwitch.")
                return

            undo = getattr(nuke, "Undo", None)
            if undo is not None:
                try:
                    undo.begin("Create Screen VariableSwitch")
                except Exception:
                    undo = None

            try:
                try:
                    switch = nuke.createNode("VariableSwitch", inpanel=False)
                except Exception:
                    switch = nuke.nodes.VariableSwitch()
            except Exception:
                self._warn_user("Unable to create a VariableSwitch node.")
                if undo:
                    try:
                        undo.end()
                    except Exception:
                        pass
                return

            try:
                switch_name = nuke.uniqueName("ScreenSwitch")
                switch.setName(switch_name)
            except Exception:
                switch_name = "ScreenSwitch"

            self._force_switch_variable_knob(switch)
            self._create_switch_inputs(switch, screens, switch_name)
            self._populate_switch_patterns(switch, screens)

            try:
                switch["label"].setValue("[value variable]")
            except Exception:
                pass

            try:
                switch.setSelected(True)
                nuke.show(switch)
            except Exception:
                pass
            finally:
                if undo is not None:
                    try:
                        undo.end()
                    except Exception:
                        pass

        def _on_default_changed(self, text: str) -> None:
            """Update the global selector `__default__.screens` to match combobox."""
            if not text:
                return
            try:
                gsv_utils.set_value("__default__.screens", text)
            except Exception:
                pass

        def _on_wrap(self) -> None:
            """Insert a VariableGroup upstream of the selected Write/Group."""

            if nuke is None or render_hooks is None:
                return
            helper = getattr(render_hooks, "encapsulate_write_with_variable_group", None)
            if helper is None:
                return
            try:
                helper()
            except Exception:
                try:
                    nuke.message("Unable to wrap the current selection; check the Script Editor for details.")
                except Exception:
                    pass

        def _force_switch_variable_knob(self, switch: object) -> None:
            """Ensure the VariableSwitch is always driven by __default__.screens."""

            try:
                switch["variable"].setValue("__default__.screens")
                return
            except Exception:
                pass
            # Fallback for versions that expect the short variable name
            try:
                switch["variable"].setValue("screens")
            except Exception:
                pass

        def _create_switch_inputs(self, switch: object, screens: Sequence[str], switch_name: str) -> None:
            """Create Dot inputs for each screen and connect them to the switch."""

            try:
                sx = int(switch["xpos"].value())
                sy = int(switch["ypos"].value())
            except Exception:
                sx, sy = 0, 0

            # Layout: dots above the switch, left-to-right by input index
            spacing_x = 120
            offset_y = 120
            count = len(screens)
            # Center the row around the switch's X
            start_x = sx - ((count - 1) * spacing_x) // 2 if count > 0 else sx
            target_y = sy - offset_y
            for idx, name in enumerate(screens):
                try:
                    dot = nuke.nodes.Dot()
                except Exception:
                    dot = None
                if dot is None:
                    continue
                try:
                    dot.setSelected(False)
                except Exception:
                    pass
                try:
                    dot_name = nuke.uniqueName(f"{switch_name}_{name}_Dot")
                    dot.setName(dot_name)
                except Exception:
                    pass
                try:
                    dot_x = start_x + idx * spacing_x
                    dot["xpos"].setValue(dot_x)
                    dot["ypos"].setValue(target_y)
                    dot["label"].setValue(name)
                except Exception:
                    pass
                try:
                    switch.setInput(idx, dot)
                except Exception:
                    pass

        def _populate_switch_patterns(self, switch: object, screens: Sequence[str]) -> None:
            """Fill every available pattern knob with the provided screen list."""

            if not screens:
                return

            patterns_knob = None
            try:
                patterns_knob = switch["patterns"]
            except Exception:
                patterns_knob = None

            if patterns_knob is not None:
                text = "\n".join(str(name) for name in screens)
                try:
                    patterns_knob.setValue(text)
                    return
                except Exception:
                    pass
                for idx, name in enumerate(screens):
                    try:
                        patterns_knob.setValueAt(str(name), idx)
                    except Exception:
                        pass

            try:
                knobs = switch.knobs()
            except Exception:
                knobs = {}

            for idx, name in enumerate(screens):
                key = f"i{idx}"
                if key in knobs:
                    try:
                        knobs[key].setValue(str(name))
                    except Exception:
                        pass

        def _warn_user(self, message: str) -> None:
            """Display a user-facing message via Nuke if available."""

            if nuke is None:
                return
            try:
                nuke.message(message)
            except Exception:
                pass


def set_default_screen_via_ui(name: str) -> bool:
    """Best-effort update of the panel's Default Screen combobox.

    Returns True when the UI was updated, False if the UI wasn't found.
    """
    if QtWidgets is None:
        return False
    try:
        # If we have a live instance, use its API
        inst = getattr(ScreensManagerPanel, "instance", None)
        if inst is not None:
            inst.set_default_screen(name)
            return True
    except Exception:
        pass
    # Fallback: locate the widget by objectName
    try:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return False
        combo = app.findChild(QtWidgets.QComboBox, "sm_default_screen")
        if combo is None:
            return False
        idx = combo.findText(name, QtCore.Qt.MatchFixedString)
        if idx < 0 and name:
            combo.addItem(name)
            idx = combo.findText(name, QtCore.Qt.MatchFixedString)
        combo.setCurrentIndex(max(0, idx))
        return True
    except Exception:
        return False


__all__ = ["ScreensManagerPanel", "set_default_screen_via_ui"]
