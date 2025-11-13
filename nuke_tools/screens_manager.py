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
            """Build and wire the minimal Qt UI."""
            layout = QtWidgets.QVBoxLayout()

            # Optional top banner logo (best-effort; ignore errors quietly)
            self.logo_label = QtWidgets.QLabel(self)
            self.logo_label.setAlignment(QtCore.Qt.AlignCenter)
            self.logo_label.setObjectName("switchManagerLogo")
            self.logo_label.setMinimumHeight(72)
            self.logo_label.setMaximumHeight(128)
            self._install_logo_pixmap()
            layout.addWidget(self.logo_label)

            # Fields area – use a simple form layout for better alignment
            form = QtWidgets.QFormLayout()

            # Screens input
            self.screens_edit = QtWidgets.QLineEdit(self)
            self.screens_edit.setPlaceholderText("Comma-separated screen names, e.g. Moxy,Godzilla,NYD400")
            self.screens_edit.setToolTip("Enter a list of screen names. Duplicates will be removed.")
            form.addRow("Screens:", self.screens_edit)

            # Default selector
            self.default_combo = QtWidgets.QComboBox(self)
            self.default_combo.setObjectName("sm_default_screen")
            self.default_combo.setToolTip("Pick the default/current screen (writes also use this unless assigned).")
            form.addRow("Default screen:", self.default_combo)

            # Buttons
            btn_row = QtWidgets.QHBoxLayout()
            self.apply_btn = QtWidgets.QPushButton("Apply to GSV", self)
            self.groups_btn = QtWidgets.QPushButton("Ensure VariableGroups", self)
            self.switch_btn = QtWidgets.QPushButton("Create VariableSwitch", self)
            self.apply_btn.setToolTip("Create/update the global screens list and default value. Also ensures screen sets.")
            self.groups_btn.setToolTip("Create a VariableGroup per screen (screen_<name>) if missing.")
            self.switch_btn.setToolTip("Create a VariableSwitch named 'ScreenSwitch' and inputs for every screen.")

            # Primary action emphasized on the left; secondary actions grouped to the right
            btn_row.addWidget(self.apply_btn, 2)
            btn_row.addStretch(1)
            btn_row.addWidget(self.groups_btn)
            btn_row.addWidget(self.switch_btn)
            self.apply_btn.setDefault(True)

            layout.addLayout(form)
            layout.addLayout(btn_row)
            layout.addStretch(1)
            self.setLayout(layout)

            # Wire signals
            self.apply_btn.clicked.connect(self._on_apply)
            self.groups_btn.clicked.connect(self._on_groups)
            self.switch_btn.clicked.connect(self._on_switch)
            # Change root selector immediately when user picks a value
            self.default_combo.currentTextChanged.connect(self._on_default_changed)

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
                logo_path = os.path.join(root_dir, "switch_manager_logo_blackpng")
                if not os.path.exists(logo_path):
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
                gsv_utils.create_variable_group(f"screen_{name}")

        def _on_switch(self) -> None:
            """Create a `VariableSwitch` named `ScreenSwitch` and auto-wire Dots.

            - Reads screens from `__default__.screens` list options.
            - Creates/positions a Dot for each screen and connects it to the
              corresponding input index on the VariableSwitch.
            - Populates the VariableSwitch `variable` to "screens" and fills
              its input patterns with the screen names (best-effort across
              potential knob layouts).
            """
            if nuke is None:
                return

            screens: List[str] = gsv_utils.get_list_options("__default__.screens")
            if not screens:
                screens = self._parse_screens()
            if not screens:
                return

            try:
                switch = nuke.nodes.VariableSwitch()
                switch_name = nuke.uniqueName("ScreenSwitch")
                switch.setName(switch_name)

                try:
                    if "variable" in switch.knobs():
                        switch["variable"].setValue("__default__.screens")
                except Exception:
                    pass

                try:
                    sx = int(switch["xpos"].value())
                    sy = int(switch["ypos"].value())
                except Exception:
                    sx, sy = 0, 0

                spacing_y = 60
                for idx, name in enumerate(screens):
                    try:
                        dot = nuke.nodes.Dot()
                    except Exception:
                        dot = None
                    if dot is None:
                        continue
                    try:
                        dot_name = nuke.uniqueName(f"{switch_name}_{name}_Dot")
                        dot.setName(dot_name)
                    except Exception:
                        pass
                    try:
                        dot["xpos"].setValue(sx - 150)
                        dot["ypos"].setValue(sy + idx * spacing_y)
                        if "label" in dot.knobs():
                            dot["label"].setValue(name)
                    except Exception:
                        pass
                    try:
                        switch.setInput(idx, dot)
                    except Exception:
                        pass

                for idx, name in enumerate(screens):
                    try:
                        switch["patterns"].setValueAt(name, idx)
                        continue
                    except Exception:
                        pass
                    try:
                        key = f"i{idx}"
                        if key in switch.knobs():
                            switch[key].setValue(name)
                    except Exception:
                        pass
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

