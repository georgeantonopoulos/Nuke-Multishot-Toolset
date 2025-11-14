"""Switch Manager panel for Nuke 16 multishot workflows.

The new Switch Manager extends the previous single-variant Screens Manager by
letting artists manage multiple GSV list variables (variants) from one panel.
Each variant owns its own options, current selection, and per-variant actions
like building VariableGroups or creating VariableSwitch previews.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence
import os

try:
    import nuke  # type: ignore
except Exception:  # pragma: no cover
    nuke = None  # type: ignore

# Try PySide6 first, then fall back to PySide2 if required.
try:  # pragma: no cover - Qt availability depends on the host
    import PySide6.QtCore as QtCore  # type: ignore
    import PySide6.QtWidgets as QtWidgets  # type: ignore
    import PySide6.QtGui as QtGui  # type: ignore
except Exception:  # pragma: no cover
    try:
        from PySide6 import QtCore as QtCore  # type: ignore
        from PySide6 import QtWidgets as QtWidgets  # type: ignore
        from PySide6 import QtGui as QtGui  # type: ignore
    except Exception:  # pragma: no cover
        try:
            import PySide2.QtCore as QtCore  # type: ignore
            import PySide2.QtWidgets as QtWidgets  # type: ignore
            import PySide2.QtGui as QtGui  # type: ignore
        except Exception:  # pragma: no cover
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

SWITCH_TILE_COLOR = 7012351


def _noop_callback() -> None:
    """Return a no-op callback."""

    return


if QtWidgets is None:

    class SwitchManagerPanel(object):  # type: ignore[misc]
        """Placeholder when Qt is unavailable."""

        def __init__(self, *args, **kwargs) -> None:  # noqa: D401
            raise RuntimeError(
                "PySide QtWidgets is not available. Cannot create SwitchManagerPanel."
            )


else:

    class VariantSectionWidget(QtWidgets.QFrame):  # type: ignore[misc]
        """Collapsible editor that manages a single variant + its options."""

        def __init__(
            self,
            change_callback: Callable[[], None],
            remove_callback: Callable[["VariantSectionWidget"], None],
            variant_name: str = "",
            options: Optional[Sequence[str]] = None,
            current_value: Optional[str] = None,
            locked: bool = False,
            parent: Optional[QtWidgets.QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self._change_callback = change_callback or _noop_callback
            self._remove_callback = remove_callback
            self._locked = False
            self._screen_name_regex = None
            if QtCore is not None and hasattr(QtCore, "QRegularExpression"):
                try:
                    self._screen_name_regex = QtCore.QRegularExpression(r"^[A-Za-z0-9_-]+$")
                except Exception:
                    self._screen_name_regex = None
            self._build_ui()
            self.set_variant_name(variant_name, emit_signal=False)
            self.set_options(options or [], current_value, emit_signal=False)
            self.set_locked(locked)

        # ------------------------------------------------------------------ UI
        def _build_ui(self) -> None:
            """Construct the collapsible UI for this variant."""

            self.setObjectName("switchVariantSection")
            self.setFrameShape(QtWidgets.QFrame.StyledPanel)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(6)

            header = QtWidgets.QHBoxLayout()
            header.setSpacing(8)

            self.collapse_btn = QtWidgets.QToolButton(self)
            self.collapse_btn.setCheckable(True)
            self.collapse_btn.setChecked(False)
            self.collapse_btn.setArrowType(QtCore.Qt.DownArrow)
            self.collapse_btn.toggled.connect(self._toggle_collapsed)
            header.addWidget(self.collapse_btn)

            self.variant_edit = QtWidgets.QLineEdit(self)
            self.variant_edit.setPlaceholderText("Variant name (e.g. screens)")
            self.variant_edit.textEdited.connect(self._on_variant_name_edited)
            header.addWidget(self.variant_edit, 1)

            current_label = QtWidgets.QLabel("Current:", self)
            current_label.setStyleSheet("color: #a0a7bb;")
            header.addWidget(current_label)

            self.current_combo = QtWidgets.QComboBox(self)
            self.current_combo.currentTextChanged.connect(self._on_default_changed)
            header.addWidget(self.current_combo, 0)

            self.remove_btn = QtWidgets.QToolButton(self)
            self.remove_btn.setText("✕")
            self.remove_btn.setAutoRaise(True)
            self.remove_btn.setToolTip("Remove this variant section.")
            self.remove_btn.clicked.connect(lambda *_: self._remove_callback(self))
            header.addWidget(self.remove_btn, 0)

            layout.addLayout(header)

            self.body = QtWidgets.QWidget(self)
            body_layout = QtWidgets.QVBoxLayout(self.body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(8)

            rows_container = QtWidgets.QWidget(self.body)
            self.rows_layout = QtWidgets.QVBoxLayout(rows_container)
            self.rows_layout.setContentsMargins(0, 0, 0, 0)
            self.rows_layout.setSpacing(4)
            body_layout.addWidget(rows_container)

            hint = QtWidgets.QLabel("Letters, numbers, underscore, and hyphen only.", self.body)
            hint.setStyleSheet("color: #8a93a5; font-size: 10px;")
            body_layout.addWidget(hint)

            self.summary_label = QtWidgets.QLabel("No options configured.", self.body)
            self.summary_label.setStyleSheet("color: #9ad8ff; font-style: italic;")
            body_layout.addWidget(self.summary_label)

            chip_container = QtWidgets.QWidget(self.body)
            self.chip_layout = QtWidgets.QHBoxLayout(chip_container)
            self.chip_layout.setContentsMargins(0, 0, 0, 0)
            self.chip_layout.setSpacing(6)
            body_layout.addWidget(chip_container)

            button_row = QtWidgets.QHBoxLayout()
            button_row.setSpacing(6)

            self.groups_btn = QtWidgets.QPushButton("Build VariableGroups", self.body)
            self.groups_btn.setToolTip("Create VariableGroups for this variant's options.")
            self.groups_btn.setFixedHeight(32)
            self.groups_btn.clicked.connect(self.build_variable_groups)
            button_row.addWidget(self.groups_btn)

            self.switch_btn = QtWidgets.QPushButton("Create VariableSwitch", self.body)
            self.switch_btn.setToolTip("Create a VariableSwitch wired to this variant.")
            self.switch_btn.setFixedHeight(32)
            self.switch_btn.clicked.connect(self.create_variable_switch)
            button_row.addWidget(self.switch_btn)

            button_row.addStretch(1)
            body_layout.addLayout(button_row)

            layout.addWidget(self.body)
            self._ensure_minimum_rows()

        # -------------------------------------------------------------- Helpers
        def variant_name(self) -> str:
            """Return the sanitized variant name."""

            return self._sanitize_name(self.variant_edit.text())

        def collect_options(self) -> List[str]:
            """Return sanitized option names from the row editors."""

            options: List[str] = []
            seen = set()
            for row in self._iter_rows():
                edit = getattr(row, "line_edit", None)
                if not isinstance(edit, QtWidgets.QLineEdit):
                    continue
                name = self._sanitize_option(edit.text())
                if name and name not in seen:
                    seen.add(name)
                    options.append(name)
            return options

        def current_selection(self) -> Optional[str]:
            """Return the active combo selection or fallback to first option."""

            try:
                text = (self.current_combo.currentText() or "").strip()
            except Exception:
                text = ""
            if text:
                return text
            options = self.collect_options()
            return options[0] if options else None

        def set_variant_name(self, text: str, emit_signal: bool = True) -> None:
            """Programmatically update the variant name."""

            clean = self._sanitize_name(text)
            if not emit_signal:
                self.variant_edit.blockSignals(True)
            self.variant_edit.setText(clean)
            if not emit_signal:
                self.variant_edit.blockSignals(False)

        def set_options(
            self,
            options: Sequence[str],
            current_value: Optional[str] = None,
            emit_signal: bool = True,
        ) -> None:
            """Rebuild the option rows and combo box."""

            options = list(options)
            self._rows_updating = True
            try:
                for row in self._iter_rows():
                    self.rows_layout.removeWidget(row)
                    row.deleteLater()
                if options:
                    for name in options:
                        self._add_row(name, emit_change=False)
                else:
                    self._ensure_minimum_rows()
            finally:
                self._rows_updating = False

            if not options:
                self._ensure_minimum_rows()

            current_options = self.collect_options()
            self._refresh_from_rows()
            self._set_combo_items(current_options, current_value, emit_signal=emit_signal)

        def is_syncable(self) -> bool:
            """Return True when the variant contains enough data to sync to GSV."""

            return bool(self.variant_name() and self.collect_options())

        def set_locked(self, locked: bool) -> None:
            """Lock or unlock the section for editing."""

            self._locked = locked
            widgets: List[QtWidgets.QWidget] = [self.variant_edit, self.current_combo]
            for row in self._iter_rows():
                edit = getattr(row, "line_edit", None)
                add_btn = getattr(row, "add_btn", None)
                remove_btn = getattr(row, "remove_btn", None)
                widgets.extend(
                    widget
                    for widget in (edit, add_btn, remove_btn)
                    if isinstance(widget, QtWidgets.QWidget)
                )
            for widget in widgets:
                try:
                    widget.setEnabled(not locked)
                except Exception:
                    pass

        # ---------------------------------------------------------- Row helpers
        def _ensure_minimum_rows(self) -> None:
            """Ensure at least two blank rows exist."""

            if hasattr(self, "_rows_updating") and self._rows_updating:
                return
            for _ in range(max(0, 2 - self.rows_layout.count())):
                self._add_row("", emit_change=False)

        def _iter_rows(self) -> List[QtWidgets.QWidget]:
            """Yield all row widgets currently in the layout."""

            rows: List[QtWidgets.QWidget] = []
            for idx in range(self.rows_layout.count()):
                item = self.rows_layout.itemAt(idx)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    rows.append(widget)
            return rows

        def _add_row(
            self,
            initial_text: str = "",
            insert_after: Optional[QtWidgets.QWidget] = None,
            emit_change: bool = True,
        ) -> QtWidgets.QWidget:
            """Insert a fresh editable row."""

            row = QtWidgets.QWidget(self.body)
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            edit = QtWidgets.QLineEdit(row)
            edit.setPlaceholderText("Option name")
            edit.setObjectName("switchVariantRow")
            if (
                QtGui is not None
                and hasattr(QtGui, "QRegularExpressionValidator")
                and self._screen_name_regex is not None
            ):
                try:
                    validator = QtGui.QRegularExpressionValidator(self._screen_name_regex, edit)
                    edit.setValidator(validator)
                except Exception:
                    pass
            edit.textEdited.connect(lambda text, editor=edit: self._sanitize_entry(editor, text))

            add_btn = QtWidgets.QToolButton(row)
            add_btn.setText("+")
            add_btn.setToolTip("Add a new option row below.")
            add_btn.setFixedSize(24, 24)
            add_btn.setAutoRaise(True)
            add_btn.clicked.connect(lambda *_args, r=row: self._add_row(insert_after=r))

            remove_btn = QtWidgets.QToolButton(row)
            remove_btn.setText("-")
            remove_btn.setToolTip("Remove this option row.")
            remove_btn.setFixedSize(24, 24)
            remove_btn.setAutoRaise(True)
            remove_btn.clicked.connect(lambda *_args, r=row: self._remove_row(r))

            row_layout.addWidget(edit, 1)
            row_layout.addWidget(add_btn, 0)
            row_layout.addWidget(remove_btn, 0)

            setattr(row, "line_edit", edit)
            setattr(row, "add_btn", add_btn)
            setattr(row, "remove_btn", remove_btn)

            if initial_text:
                edit.setText(self._sanitize_option(initial_text))

            insert_index = self.rows_layout.count()
            if insert_after is not None:
                idx = self.rows_layout.indexOf(insert_after)
                if idx >= 0:
                    insert_index = idx + 1
            self.rows_layout.insertWidget(insert_index, row)

            if emit_change:
                self._refresh_from_rows()
            return row

        def _remove_row(self, row: QtWidgets.QWidget) -> None:
            """Remove a row widget (leaving at least one blank row)."""

            rows = self._iter_rows()
            if len(rows) <= 1:
                edit = getattr(row, "line_edit", None)
                if isinstance(edit, QtWidgets.QLineEdit):
                    edit.clear()
                self._refresh_from_rows()
                return
            self.rows_layout.removeWidget(row)
            row.deleteLater()
            self._refresh_from_rows()

        def _sanitize_entry(self, edit: QtWidgets.QLineEdit, text: str) -> None:
            """Filter invalid characters during typing."""

            raw = text or ""
            cursor = edit.cursorPosition()
            allowed = "_-"
            clean_chars: List[str] = []
            removed_before_cursor = 0
            for idx, ch in enumerate(raw):
                if ch.isalnum() or ch in allowed:
                    clean_chars.append(ch)
                else:
                    if idx < cursor:
                        removed_before_cursor += 1
            clean = "".join(clean_chars)
            if clean != raw:
                new_cursor = max(0, cursor - removed_before_cursor)
                edit.blockSignals(True)
                edit.setText(clean)
                edit.setCursorPosition(new_cursor)
                edit.blockSignals(False)
            self._refresh_from_rows()

        # ------------------------------------------------------- State helpers
        def _toggle_collapsed(self, collapsed: bool) -> None:
            """Show/hide the body widget when the header is toggled."""

            self.collapse_btn.setArrowType(QtCore.Qt.RightArrow if collapsed else QtCore.Qt.DownArrow)
            self.body.setVisible(not collapsed)

        def _sanitize_name(self, text: Optional[str]) -> str:
            """Sanitize variant name."""

            value = (text or "").strip()
            return "".join(ch for ch in value if ch.isalnum() or ch in "_-")

        def _sanitize_option(self, text: Optional[str]) -> str:
            """Sanitize an option entry."""

            value = (text or "").strip()
            return "".join(ch for ch in value if ch.isalnum() or ch in "_-")

        def _set_combo_items(
            self, options: Sequence[str], current_value: Optional[str], emit_signal: bool = True
        ) -> None:
            """Update the combo box items."""

            if not isinstance(self.current_combo, QtWidgets.QComboBox):
                return
            try:
                self.current_combo.blockSignals(True)
                self.current_combo.clear()
                for name in options:
                    self.current_combo.addItem(name)
                target = current_value if current_value in options else (options[0] if options else "")
                if target:
                    idx = self.current_combo.findText(target, QtCore.Qt.MatchFixedString)
                    if idx >= 0:
                        self.current_combo.setCurrentIndex(idx)
                    else:
                        self.current_combo.setCurrentText(target)
            finally:
                if emit_signal:
                    self.current_combo.blockSignals(False)
                else:
                    self.current_combo.blockSignals(False)

        def _refresh_from_rows(self) -> None:
            """Refresh combo items, summary text, and chips."""

            if getattr(self, "_rows_updating", False):
                return
            options = self.collect_options()
            self._set_combo_items(options, self.current_selection(), emit_signal=False)
            self._update_summary(options)
            self._render_chips(options)
            self._change_callback()

        def _update_summary(self, options: Sequence[str]) -> None:
            """Update helper text summarizing option count."""

            count = len(options)
            if count == 0:
                summary = "No options configured."
            elif count == 1:
                summary = f"1 option: {options[0]}"
            elif count <= 4:
                summary = f"{count} options • {', '.join(options)}"
            else:
                summary = f"{count} options • {', '.join(options[:3])}…"
            self.summary_label.setText(summary)

        def _render_chips(self, options: Sequence[str]) -> None:
            """Render small chips for the options."""

            while self.chip_layout.count():
                item = self.chip_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            if not options:
                placeholder = QtWidgets.QLabel("Add options to preview them here.")
                placeholder.setStyleSheet("color: #6c788d;")
                self.chip_layout.addWidget(placeholder)
                self.chip_layout.addStretch(1)
                return
            for name in options:
                chip = QtWidgets.QLabel(name)
                chip.setStyleSheet(
                    "background-color: #2f3542; border-radius: 10px; padding: 4px 10px; color: #f0f6ff;"
                )
                self.chip_layout.addWidget(chip)
            self.chip_layout.addStretch(1)

        # -------------------------------------------------------- Event hooks
        def _on_variant_name_edited(self, text: str) -> None:
            """Respond to variant name edits."""

            clean = self._sanitize_name(text)
            if clean != text:
                cursor = self.variant_edit.cursorPosition()
                self.variant_edit.blockSignals(True)
                self.variant_edit.setText(clean)
                self.variant_edit.setCursorPosition(min(cursor, len(clean)))
                self.variant_edit.blockSignals(False)
            self._change_callback()

        def _on_default_changed(self, _text: str) -> None:
            """Notify parent panel when the selection changes."""

            self._change_callback()

        # ----------------------------------------------------- Variant actions
        def apply_to_gsv(self) -> None:
            """Write this variant + options back to the root GSV."""

            variant = self.variant_name()
            options = self.collect_options()
            if not variant or not options:
                return
            gsv_utils.ensure_variant_list(variant, options, self.current_selection())
            gsv_utils.ensure_option_sets(options)

        def build_variable_groups(self) -> None:
            """Create VariableGroup scaffolding for each option."""

            variant = self.variant_name()
            if not variant:
                self._show_message("Set a variant name before building VariableGroups.")
                return
            options = self.collect_options()
            if not options:
                self._show_message("Add at least one option before building VariableGroups.")
                return
            for name in options:
                node = gsv_utils.create_variable_group(self._group_node_name(name))
                if node is None:
                    continue
                try:
                    node["gsv"].setGsvValue(f"__default__.{variant}", str(name))
                except Exception:
                    pass

        def create_variable_switch(self) -> None:
            """Create a VariableSwitch limited to this variant's options."""

            if nuke is None:
                return
            variant = self.variant_name()
            options = self.collect_options()
            if not variant or not options:
                self._show_message("Add a variant name and at least one option first.")
                return

            undo = getattr(nuke, "Undo", None)
            if undo is not None:
                try:
                    undo.begin(f"Create {variant} VariableSwitch")
                except Exception:
                    undo = None

            try:
                try:
                    switch = nuke.createNode("VariableSwitch", inpanel=False)
                except Exception:
                    switch = nuke.nodes.VariableSwitch()
            except Exception:
                self._show_message("Unable to create a VariableSwitch node.")
                if undo is not None:
                    try:
                        undo.end()
                    except Exception:
                        pass
                return

            switch_name = f"VariableSwitch_{variant}"
            try:
                switch_name = nuke.uniqueName(switch_name)
                switch.setName(switch_name)
            except Exception:
                try:
                    switch_name = switch.name()
                except Exception:
                    switch_name = f"VariableSwitch_{variant}"

            self._force_switch_variable(switch, variant)
            self._create_switch_inputs(switch, options, switch_name)
            self._populate_switch_patterns(switch, options)
            self._style_variable_switch(switch)

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

        # ------------------------------------------------- VariableSwitch util
        def _force_switch_variable(self, switch: object, variant: str) -> None:
            """Force the VariableSwitch to reference this variant path."""

            try:
                switch["variable"].setValue(f"__default__.{variant}")
                return
            except Exception:
                pass
            try:
                switch["variable"].setValue(variant)
            except Exception:
                pass

        def _create_switch_inputs(
            self, switch: object, options: Sequence[str], switch_name: str
        ) -> None:
            """Create Dot nodes for each option and connect them to the switch."""

            try:
                sx = int(switch["xpos"].value())
                sy = int(switch["ypos"].value())
            except Exception:
                sx, sy = 0, 0

            spacing_x = 120
            offset_y = 120
            count = len(options)
            start_x = sx - ((count - 1) * spacing_x) // 2 if count > 0 else sx
            target_y = sy - offset_y
            for idx, name in enumerate(options):
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
                    dot["xpos"].setValue(start_x + idx * spacing_x)
                    dot["ypos"].setValue(target_y)
                    dot["label"].setValue(name)
                except Exception:
                    pass
                try:
                    switch.setInput(idx, dot)
                except Exception:
                    pass

        def _populate_switch_patterns(self, switch: object, options: Sequence[str]) -> None:
            """Populate the VariableSwitch pattern knob with option names."""

            if not options:
                return
            patterns = None
            try:
                patterns = switch["patterns"]
            except Exception:
                patterns = None
            if patterns is not None:
                text = "\n".join(str(name) for name in options)
                try:
                    patterns.setValue(text)
                    return
                except Exception:
                    pass
            try:
                knobs = switch.knobs()
            except Exception:
                knobs = {}
            for idx, name in enumerate(options):
                key = f"i{idx}"
                knob = knobs.get(key)
                if knob is None:
                    continue
                try:
                    knob.setValue(str(name))
                except Exception:
                    pass

        def _style_variable_switch(self, switch: object) -> None:
            """Apply consistent labeling/color to the created VariableSwitch."""

            try:
                switch["label"].setValue("[value variable]")
            except Exception:
                pass
            try:
                switch["tile_color"].setValue(SWITCH_TILE_COLOR)
            except Exception:
                pass
            try:
                switch["node_font_color"].setValue(4294967295)
            except Exception:
                pass

        # ----------------------------------------------------------- Utilities
        def _group_node_name(self, option_name: str) -> str:
            """Return a readable VariableGroup node name for this variant/option."""

            variant = self.variant_name() or "variant"
            if variant == "screens":
                prefix = "screen"
            else:
                prefix = variant
            return f"{prefix}_{option_name}"

        def _show_message(self, message: str) -> None:
            """Display a user-visible message via Nuke."""

            if nuke is None:
                return
            try:
                nuke.message(message)
            except Exception:
                pass

    class SwitchManagerPanel(QtWidgets.QWidget):  # type: ignore[misc]
        """Dockable Switch Manager that orchestrates multiple variants."""

        instance: Optional["SwitchManagerPanel"] = None

        def __init__(self, parent=None) -> None:  # noqa: D401
            super().__init__(parent)
            self.setWindowTitle("Switch Manager")
            self.setObjectName("SwitchManagerPanel")
            SwitchManagerPanel.instance = self
            self._is_synced = False
            self._sections_locked = False
            self._status_timer = None
            self._focus_tracking_ready = False
            self._build_ui()
            self._load_from_gsv()
            self._install_gsv_callback()
            self._install_focus_tracking()
            self._update_sync_status(force=True)

        # ----------------------------------------------------------------- UI
        def _build_ui(self) -> None:
            """Construct the panel UI."""

            self.setMinimumWidth(460)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            layout.addWidget(self._build_header())

            hero = QtWidgets.QLabel(
                "Create variations, sync list variables, and wire VariableGroups or Switch nodes per option."
            )
            hero.setWordWrap(True)
            hero.setStyleSheet("color: #d6d6d6; font-size: 11px;")
            layout.addWidget(hero)

            self.sections_holder = QtWidgets.QWidget(self)
            self.sections_layout = QtWidgets.QVBoxLayout(self.sections_holder)
            self.sections_layout.setContentsMargins(0, 0, 0, 0)
            self.sections_layout.setSpacing(12)
            layout.addWidget(self.sections_holder)

            self.add_variant_btn = QtWidgets.QPushButton("+ Add Variant", self)
            self.add_variant_btn.setToolTip("Add another variant / option set.")
            self.add_variant_btn.setFixedHeight(32)
            self.add_variant_btn.clicked.connect(lambda *_: self._add_variant_section())
            layout.addWidget(self.add_variant_btn, 0)

            actions = QtWidgets.QGroupBox("Quick Actions", self)
            actions_layout = QtWidgets.QGridLayout(actions)
            actions_layout.setHorizontalSpacing(8)
            actions_layout.setVerticalSpacing(8)

            self.sync_btn = QtWidgets.QPushButton("Sync Options to GSV", actions)
            self.edit_btn = QtWidgets.QPushButton("Edit GSV", actions)
            self.wrap_btn = QtWidgets.QPushButton("Lock Write node to Options", actions)

            self._style_action_button(self.sync_btn, role="primary")
            self._style_action_button(self.edit_btn, role="secondary")
            self._style_action_button(self.wrap_btn, role="accent")

            actions_layout.addWidget(self.sync_btn, 0, 0, 1, 2)
            actions_layout.addWidget(self.edit_btn, 1, 0, 1, 2)
            layout.addWidget(actions)

            layout.addWidget(self.wrap_btn)

            layout.addStretch(1)
            layout.addWidget(self._build_status_bar())

            self.sync_btn.clicked.connect(self._on_sync)
            self.edit_btn.clicked.connect(self._on_edit)
            self.wrap_btn.clicked.connect(self._on_wrap)

        def _build_header(self) -> QtWidgets.QWidget:
            """Return the branded header widget."""

            header = QtWidgets.QFrame(self)
            header.setObjectName("switchManagerHeader")
            header.setStyleSheet(
                """
                QFrame#switchManagerHeader {
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
            self.logo_label.setMinimumSize(72, 72)
            self.logo_label.setMaximumHeight(128)
            self._install_logo_pixmap()
            layout.addWidget(self.logo_label, 0)

            title_block = QtWidgets.QVBoxLayout()
            title = QtWidgets.QLabel("Switch Manager", header)
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
            """Apply consistent styling to the main action buttons."""

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

        def _install_logo_pixmap(self) -> None:
            """Load the branded PNG, if available."""

            if QtGui is None:
                return
            try:
                this_dir = os.path.dirname(os.path.abspath(__file__))
                root_dir = os.path.dirname(this_dir)
                candidates = [os.path.join(root_dir, "switch_manager_logo_alpha.png")]
                path = next((p for p in candidates if os.path.exists(p)), None)
                if path is None:
                    return
                self._logo_pixmap = QtGui.QPixmap(path)
                if not self._logo_pixmap.isNull():
                    scaled = self._logo_pixmap.scaledToHeight(96, QtCore.Qt.SmoothTransformation)
                    self.logo_label.setPixmap(scaled)
            except Exception:
                pass

        def resizeEvent(self, event):  # type: ignore[override]
            """Keep the header image nicely scaled."""

            try:
                if QtGui is not None and hasattr(self, "_logo_pixmap"):
                    max_height = max(72, min(128, int(self.height() * 0.18)))
                    scaled = self._logo_pixmap.scaledToHeight(
                        max_height, QtCore.Qt.SmoothTransformation
                    )
                    self.logo_label.setPixmap(scaled)
            except Exception:
                pass
            super().resizeEvent(event)

        # -------------------------------------------------------- Sections API
        def _add_variant_section(
            self,
            variant_name: str = "",
            options: Optional[Sequence[str]] = None,
            current_value: Optional[str] = None,
            locked: Optional[bool] = None,
        ) -> VariantSectionWidget:
            """Create and add a new variant section widget."""

            locked_flag = self._sections_locked if locked is None else bool(locked)
            section = VariantSectionWidget(
                change_callback=self._mark_unsynced,
                remove_callback=self._remove_section,
                variant_name=variant_name,
                options=options or [],
                current_value=current_value,
                locked=locked_flag,
                parent=self.sections_holder,
            )
            self.sections_layout.addWidget(section)
            return section

        def _remove_section(self, section: VariantSectionWidget) -> None:
            """Remove a variant section from the layout."""

            widgets = self._section_widgets()
            if len(widgets) <= 1:
                section.set_variant_name("", emit_signal=False)
                section.set_options([], emit_signal=False)
                self._set_sections_locked(False)
                self._mark_unsynced()
                return
            self.sections_layout.removeWidget(section)
            section.deleteLater()
            self._mark_unsynced()

        def _section_widgets(self) -> List[VariantSectionWidget]:
            """Return every VariantSectionWidget currently displayed."""

            widgets: List[VariantSectionWidget] = []
            for idx in range(self.sections_layout.count()):
                item = self.sections_layout.itemAt(idx)
                if item is None:
                    continue
                widget = item.widget()
                if isinstance(widget, VariantSectionWidget):
                    widgets.append(widget)
            return widgets

        def _clear_sections(self) -> None:
            """Remove all variant sections."""

            for widget in self._section_widgets():
                self.sections_layout.removeWidget(widget)
                widget.deleteLater()

        # ------------------------------------------------------ Status helpers
        def _build_status_bar(self) -> QtWidgets.QFrame:
            """Create the status indicator shown at the bottom of the panel."""

            status_bar = QtWidgets.QFrame(self)
            status_bar.setObjectName("switchManagerStatusBar")
            status_bar.setStyleSheet(
                """
                QFrame#switchManagerStatusBar {
                    border: 1px solid #2f3847;
                    border-radius: 6px;
                    background-color: #1b1f27;
                    padding: 8px 12px;
                }
                """
            )
            layout = QtWidgets.QHBoxLayout(status_bar)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            self.status_icon_label = QtWidgets.QLabel("[!]", status_bar)
            self.status_icon_label.setObjectName("switchManagerStatusIcon")
            self.status_icon_label.setStyleSheet("color: #f2c14e; font-weight: 700;")
            self.status_text_label = QtWidgets.QLabel("GSV status pending…", status_bar)
            self.status_text_label.setObjectName("switchManagerStatusText")
            self.status_text_label.setStyleSheet("color: #9ad8ff; font-weight: 500;")
            layout.addWidget(self.status_icon_label, 0)
            layout.addWidget(self.status_text_label, 1)
            status_bar.setToolTip("Live sync state between this panel and the Global Variables.")
            self.status_bar = status_bar
            return status_bar

        def _install_focus_tracking(self) -> None:
            """Start polling for status changes only when the panel is in focus."""

            if QtCore is None or QtWidgets is None:
                return
            if getattr(self, "_focus_tracking_ready", False):
                return
            timer = QtCore.QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(self._update_sync_status)
            self._status_timer = timer
            app = QtWidgets.QApplication.instance()
            if app is not None:
                try:
                    app.focusChanged.connect(self._on_focus_changed)  # type: ignore[arg-type]
                except Exception:
                    pass
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            self._focus_tracking_ready = True

        def _on_focus_changed(
            self, _old: Optional[QtWidgets.QWidget], new: Optional[QtWidgets.QWidget]
        ) -> None:
            """Start/stop polling when focus enters or leaves the panel."""

            if self._widget_within_panel(new):
                self._start_status_timer()
                self._update_sync_status(force=True)
                return
            if not self._panel_has_focus():
                self._stop_status_timer()

        def _widget_within_panel(self, widget: Optional[QtWidgets.QWidget]) -> bool:
            """Return True when the widget belongs to this panel."""

            if widget is None:
                return False
            if widget is self:
                return True
            try:
                return self.isAncestorOf(widget)
            except Exception:
                return False

        def _panel_has_focus(self) -> bool:
            """Return True when the panel (or a child) currently has focus."""

            if QtWidgets is None:
                return False
            app = QtWidgets.QApplication.instance()
            if app is None:
                return False
            widget = app.focusWidget()
            return self._widget_within_panel(widget)

        def _start_status_timer(self) -> None:
            """Begin periodic status checks."""

            timer = self._status_timer
            if timer is None:
                return
            if timer.isActive():
                return
            try:
                timer.start()
            except Exception:
                pass

        def _stop_status_timer(self) -> None:
            """Stop periodic status checks."""

            timer = self._status_timer
            if timer is None:
                return
            try:
                timer.stop()
            except Exception:
                pass

        def _update_sync_status(self, force: bool = False) -> None:
            """Refresh the status bar, optionally bypassing the focus gate."""

            if not force and not self._panel_has_focus():
                return
            synced = self._gsv_state_matches_ui()
            if synced != self._is_synced:
                self._is_synced = synced
                if synced:
                    self._render_status_message(True)
                else:
                    self._render_status_message(False)
            elif force:
                self._render_status_message(synced)

        def _gsv_state_matches_ui(self) -> bool:
            """Return True when UI variants/options mirror the root GSV."""

            gsv_variants = gsv_utils.discover_list_variants()
            section_map: Dict[str, VariantSectionWidget] = {}
            for section in self._section_widgets():
                name = section.variant_name()
                options = section.collect_options()
                if not name and any(options):
                    return False
                if name:
                    if name in section_map:
                        return False
                    section_map[name] = section
            if set(section_map.keys()) != set(gsv_variants.keys()):
                return False
            for name, section in section_map.items():
                ui_options = section.collect_options()
                if ui_options != gsv_variants.get(name, []):
                    return False
                ui_current = (section.current_selection() or "").strip()
                gsv_current = (gsv_utils.get_variant_value(name) or "").strip()
                if ui_current != gsv_current:
                    return False
            return True

        def _render_status_message(self, synced: bool) -> None:
            """Update the status icon/text to match the provided state."""

            icon_lbl = getattr(self, "status_icon_label", None)
            text_lbl = getattr(self, "status_text_label", None)
            if not isinstance(icon_lbl, QtWidgets.QLabel) or not isinstance(
                text_lbl, QtWidgets.QLabel
            ):
                return
            if synced:
                icon_lbl.setText("[OK]")
                icon_lbl.setStyleSheet("color: #4bc27d; font-weight: 700;")
                text_lbl.setText("GSV synced")
                text_lbl.setStyleSheet("color: #4bc27d; font-weight: 600;")
            else:
                icon_lbl.setText("[!]")
                icon_lbl.setStyleSheet("color: #ff6b6b; font-weight: 700;")
                text_lbl.setText("GSV not synced")
                text_lbl.setStyleSheet("color: #ff6b6b; font-weight: 600;")

        def _set_sections_locked(self, locked: bool) -> None:
            """Lock/unlock all variant sections and related controls."""

            locked_flag = bool(locked)
            self._sections_locked = locked_flag
            for section in self._section_widgets():
                section.set_locked(locked_flag)
            edit_btn = getattr(self, "edit_btn", None)
            if isinstance(edit_btn, QtWidgets.QPushButton):
                edit_btn.setEnabled(locked_flag)
            add_btn = getattr(self, "add_variant_btn", None)
            if isinstance(add_btn, QtWidgets.QPushButton):
                add_btn.setEnabled(not locked_flag)

        # ----------------------------------------------------------- GSV sync
        def _load_from_gsv(self) -> None:
            """Rebuild the UI from current GSV list variants."""

            variants = gsv_utils.discover_list_variants()
            self._clear_sections()
            if not variants:
                self._add_variant_section()
                self._set_sections_locked(False)
                self._mark_unsynced()
                return
            for name in sorted(variants.keys()):
                options = variants.get(name, [])
                current = gsv_utils.get_variant_value(name)
                section = self._add_variant_section(name, options, current, locked=True)
                section.set_locked(True)
            self._set_sections_locked(True)
            self._mark_synced()

        def _install_gsv_callback(self) -> None:
            """Keep the panel in sync with the root GSV knob."""

            if nuke is None:
                return
            try:
                callbacks = getattr(nuke, "callbacks", None)
                if callbacks and hasattr(callbacks, "onGsvSetChanged"):
                    def _handler(*_args, **_kwargs):
                        try:
                            self._load_from_gsv()
                        except Exception:
                            pass

                    callbacks.onGsvSetChanged(_handler)
            except Exception:
                pass

        def _mark_synced(self) -> None:
            """Update the status label to show a synced state."""

            self._is_synced = True
            self._render_status_message(True)
            self._set_sections_locked(True)

        def _mark_unsynced(self) -> None:
            """Update the status label to show the panel needs syncing."""

            self._is_synced = False
            self._render_status_message(False)

        # -------------------------------------------------------------- Actions
        def _on_sync(self) -> None:
            """Sync every valid variant back to GSV."""

            existing_variants = set(gsv_utils.discover_list_variants().keys())
            synced_variants: set[str] = set()

            wrote_any = False
            for section in self._section_widgets():
                if not section.is_syncable():
                    continue
                section.apply_to_gsv()
                synced_variants.add(section.variant_name())
                wrote_any = True

            removed_variants = existing_variants - synced_variants
            for variant in removed_variants:
                gsv_utils.remove_variant(variant)

            if removed_variants:
                wrote_any = True

            if wrote_any:
                self._load_from_gsv()

        def _on_edit(self) -> None:
            """Unlock all variant sections for editing."""

            self._set_sections_locked(False)
            self._update_sync_status(force=True)

        def _on_wrap(self) -> None:
            """Wrap the selected Write/Group with a VariableGroup."""

            if nuke is None or render_hooks is None:
                return
            helper = getattr(render_hooks, "encapsulate_write_with_variable_group", None)
            if helper is None:
                return
            try:
                helper()
            except Exception:
                try:
                    nuke.message(
                        "Unable to wrap the current selection; check the Script Editor for details."
                    )
                except Exception:
                    pass

        # ---------------------------------------------------------- Panel API
        def get_active_variant_values(self) -> Dict[str, str]:
            """Return {variant: selection} for all configured variants."""

            values: Dict[str, str] = {}
            for section in self._section_widgets():
                name = section.variant_name()
                current = section.current_selection()
                if name and current:
                    values[name] = current
            return values

        def set_default_variant_value(self, variant: str, value: str) -> bool:
            """Update the combo box for the requested variant, if it exists."""

            for section in self._section_widgets():
                if section.variant_name() == variant:
                    options = section.collect_options()
                    if value and value not in options:
                        options.append(value)
                    section.set_options(options, current_value=value, emit_signal=False)
                    return True
            # Variant not found—add a new section to host it.
            section = self._add_variant_section(variant_name=variant, options=[value], current_value=value)
            section.set_locked(False)
            return True


def set_default_screen_via_ui(name: str) -> bool:
    """Update the Switch Manager UI for the legacy `screens` variant."""

    if QtWidgets is None:
        return False
    inst = getattr(SwitchManagerPanel, "instance", None)
    if inst is not None:
        return inst.set_default_variant_value("screens", name)
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    panel = app.findChild(QtWidgets.QWidget, "SwitchManagerPanel")
    if panel is None or not hasattr(panel, "set_default_variant_value"):
        return False
    try:
        panel.set_default_variant_value("screens", name)
        return True
    except Exception:
        return False


__all__ = ["SwitchManagerPanel", "set_default_screen_via_ui"]
