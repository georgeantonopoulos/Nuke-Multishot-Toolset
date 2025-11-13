"""Helpers to wrap Write nodes into VariableGroups for per-screen workflows.

This module provides a concise, strategy-based promoter that:
- Collapses a selected Write (or publishable Group) into a VariableGroup
- Exposes a minimal, editable knob whitelist on the wrapper's UI
- Adds a small management tab with checkbox toggles and a Refresh button

Dynamic syncing and tab introspection have been removed to reduce complexity.
Artists can adjust the whitelist in the wrapper and click Refresh to re-expose
knobs as desired.
"""
import re

import nuke
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from . import gsv_utils


# Knobs that should not be promoted because the VariableGroup already provides
# its own versions or they are positional/housekeeping values.
_RESERVED_KNOBS = {
    "name",
    "label",
    "xpos",
    "ypos",
    "selected",
    "hide_input",
    "note_font",
    "note_font_size",
    "note_font_color",
    "tile_color",
    "gl_color",
    "cached",
    "knobChanged",
    "help",
    "onCreate",
    "onDestroy",
    "node_class",
}

# Minimal default whitelist; artists can extend via the wrapper tab.
_DEFAULT_WRITE_KNOBS: List[str] = [
    "file",
    "file_type",
    "channels",
    "views",
    "colorspace",
    "proxy",
    "first",
    "last",
    "use_limit",
    "create_directories",
]

_BCN_MANAGEMENT_TAB = "bcn_wrapper"
_BCN_MANAGEMENT_LABEL = "BCN Wrapper"
_WHITELIST_TOGGLE_PREFIX = "bcn_whitelist__"
_SCREEN_SELECTOR_KNOB = "bcn_screen_selector"
_SCREEN_SELECTOR_CALLBACK_SNIPPET = (
    "import nuke\n"
    "if knob and knob.name() == \"{}\":\n"
    "    import BCN_multishot_toolset.nuke_tools.render_hooks as rh\n"
    "    rh._on_screen_selector_changed(nuke.thisNode(), knob.value())\n"
).format(_SCREEN_SELECTOR_KNOB)
_TOGGLE_TOOLTIP_PATTERN = re.compile(r"Expose the '([^']+)' knob")


def _sanitize_knob_scripts(node: object) -> None:
    """Remove legacy 'python:' prefixes from script-like knobs on a node.

    This cleans up older wrappers that may still carry script strings starting
    with 'python:' which cause SyntaxError on execution in modern Nuke.
    """

    try:
        knobs = getattr(node, "knobs")()
    except Exception:
        return
    for kname, knob in list(knobs.items()):
        try:
            # Only process knobs that can carry string values
            if hasattr(knob, "value"):
                val = knob.value()
            else:
                continue
            if not isinstance(val, str):
                continue
            txt = val.lstrip()
            if txt.startswith("python:"):
                # Drop only the leading prefix label
                cleaned = txt[len("python:"):].lstrip("\n\r ")
                knob.setValue(cleaned)
        except Exception:
            continue


def _sanitize_group_knob_scripts(group: object) -> None:
    """Sanitize script-like knobs on the wrapper and all internal nodes.

    Removes legacy "python:" prefixes that can cause SyntaxError.
    """

    # Sanitize the wrapper itself
    try:
        _sanitize_knob_scripts(group)
    except Exception:
        pass
    # Sanitize internal nodes (recurse into subgroups)
    try:
        with group:
            for n in list(nuke.allNodes(recurse=True)):  # type: ignore[attr-defined]
                try:
                    _sanitize_knob_scripts(n)
                except Exception:
                    continue
    except Exception:
        pass


def _ensure_tab(group: object, name: str, label: str):
    """Ensure a `Tab_Knob` with the given name exists on the group."""

    knobs = getattr(group, "knobs")()
    if name in knobs:
        return knobs[name]
    tab = nuke.Tab_Knob(name, label)  # type: ignore[attr-defined]
    group.addKnob(tab)
    return tab


def _activate_tab(group: object, name: str) -> bool:
    """Attempt to make `name` the active tab for subsequent knob additions."""

    set_tab = getattr(group, "setTab", None)
    if not callable(set_tab):
        return False
    try:
        set_tab(name)
        return True
    except TypeError:
        pass
    except Exception:
        return False

    knobs = getattr(group, "knobs")()
    target = knobs.get(name)
    if target is not None:
        try:
            set_tab(target)
            return True
        except Exception:
            pass
    try:
        ordered = list(knobs.values())
        for idx, knob in enumerate(ordered):
            try:
                if knob.Class() == "Tab_Knob" and knob.name() == name:
                    set_tab(idx)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _add_link_knob(group: object, src_node: object, name: str, label: Optional[str]) -> bool:
    """Create a `Link_Knob` on `group` that targets `src_node[name]`.

    Returns True if a link was added, False otherwise.
    """

    if name in _RESERVED_KNOBS:
        return False
    if name in group.knobs():
        return False
    if name not in getattr(src_node, "knobs")():
        return False
    link = nuke.Link_Knob(name, label or name)  # type: ignore[attr-defined]
    # Try linking by object; fallback to string-based linking.
    made = False
    try:
        link.makeLink(src_node, name)
        made = True
    except TypeError:
        pass
    if not made:
        node_name: Optional[str] = None
        try:
            if hasattr(src_node, "fullName"):
                node_name = str(src_node.fullName())
        except Exception:
            node_name = None
        if not node_name:
            try:
                if hasattr(src_node, "name"):
                    node_name = str(src_node.name())
            except Exception:
                node_name = None
        if node_name:
            link.makeLink(node_name, name)
            made = True
    if not made:
        return False
    group.addKnob(link)
    return True


def _toggle_knob_name(knob_name: str) -> str:
    """Return a stable Boolean knob name for a write knob entry."""

    safe = re.sub(r"[^0-9A-Za-z_]+", "_", knob_name.strip()) or "item"
    return f"{_WHITELIST_TOGGLE_PREFIX}{safe}"


def _label_for_write_knob(write_node: object, knob_name: str) -> str:
    """Derive a user-facing label for a write knob checkbox."""

    try:
        knob = write_node[knob_name]
        if hasattr(knob, "label"):
            label = knob.label()
            if label:
                return label
    except Exception:
        pass
    pretty = knob_name.replace("_", " ").strip()
    return pretty.title() if pretty else knob_name


def _whitelist_tooltip(knob_name: str) -> str:
    """Tooltip text carrying the original knob name (used for lookups)."""

    return f"Expose the '{knob_name}' knob on this wrapper"


def _original_name_from_toggle(toggle_name: str, toggle: object) -> str:
    """Recover the original write knob name from a toggle knob."""

    tooltip = ""
    try:
        if hasattr(toggle, "tooltip"):
            tooltip = toggle.tooltip() or ""
    except Exception:
        tooltip = ""
    match = _TOGGLE_TOOLTIP_PATTERN.search(tooltip)
    if match:
        return match.group(1)
    # Fallback: strip the prefix and normalize underscores back to spaces
    raw = toggle_name[len(_WHITELIST_TOGGLE_PREFIX):]
    return raw.replace("__", "_")


def _ensure_management_tab(group: object, knob_order: Sequence[str], write_node: object) -> None:
    """Add/update the BCN wrapper tab with checkbox whitelist and refresh button."""

    _ensure_tab(group, _BCN_MANAGEMENT_TAB, _BCN_MANAGEMENT_LABEL)
    _activate_tab(group, _BCN_MANAGEMENT_TAB)

    knobs = getattr(group, "knobs")()

    csv_selected: Optional[set] = None
    legacy_name = "bcn_knob_whitelist"
    if legacy_name in knobs:
        try:
            raw = knobs[legacy_name].value()
            if isinstance(raw, str) and raw.strip():
                csv_selected = {s.strip() for s in raw.split(",") if s.strip()}
        except Exception:
            csv_selected = None
        try:
            group.removeKnob(knobs[legacy_name])
        except Exception:
            pass
        knobs.pop(legacy_name, None)

    if "bcn_label" not in knobs:
        label = nuke.Text_Knob("bcn_label", "Write knob whitelist")  # type: ignore[attr-defined]
        label.setTooltip("Toggle which internal Write knobs should be exposed on the wrapper's Write tab.")
        group.addKnob(label)

    keep_names = set()
    for knob_name in knob_order:
        toggle_name = _toggle_knob_name(knob_name)
        keep_names.add(toggle_name)
        label = _label_for_write_knob(write_node, knob_name)
        existing = knobs.get(toggle_name)
        if existing is None:
            toggle = nuke.Boolean_Knob(toggle_name, label)  # type: ignore[attr-defined]
            toggle.setTooltip(_whitelist_tooltip(knob_name))
            if csv_selected is not None:
                toggle.setValue(knob_name in csv_selected)
            else:
                toggle.setValue(True)
            group.addKnob(toggle)
            knobs[toggle_name] = toggle
        else:
            try:
                existing.setLabel(label)
                existing.setTooltip(_whitelist_tooltip(knob_name))
                if csv_selected is not None:
                    existing.setValue(knob_name in csv_selected)
                existing.setVisible(True)
            except Exception:
                pass

    # Hide any stale toggles that are no longer applicable
    for name, knob in list(knobs.items()):
        if name.startswith(_WHITELIST_TOGGLE_PREFIX) and name not in keep_names:
            try:
                knob.setVisible(False)
            except Exception:
                pass

    cmd = (
        "import nuke\n"
        "import BCN_multishot_toolset.nuke_tools.render_hooks as rh\n"
        "rh.refresh_variable_group_links(nuke.thisNode())\n"
    )
    if "bcn_refresh" not in knobs:
        button = nuke.PyScript_Knob("bcn_refresh", "Refresh Links")  # type: ignore[attr-defined]
        button.setCommand(cmd)
        button.setTooltip("Rebuild the Write tab links using the enabled checkboxes above")
        group.addKnob(button)
    else:
        try:
            knobs["bcn_refresh"].setCommand(cmd)
        except Exception:
            pass


def _get_group_screen(group: object) -> Optional[str]:
    """Return the `__default__.screens` value stored on the VariableGroup."""

    try:
        gsv = group["gsv"]
        return gsv.getGsvValue("__default__.screens")
    except Exception:
        return None


def _set_group_screen(group: object, screen: Optional[str]) -> None:
    """Assign `screen` to the VariableGroup-local GSV."""

    if not screen:
        return
    try:
        gsv = group["gsv"]
        gsv.setGsvValue("__default__.screens", str(screen))
    except Exception:
        pass


def _install_screen_selector_callback(group: object) -> None:
    """Ensure the knobChanged script updates the local screen when selector changes."""

    try:
        script_knob = group["knobChanged"]
    except Exception:
        return
    try:
        current = script_knob.value()
    except Exception:
        current = ""
    current = current or ""
    if _SCREEN_SELECTOR_CALLBACK_SNIPPET in current:
        return
    new_script = current.rstrip()
    if new_script and not new_script.endswith("\n"):
        new_script += "\n"
    new_script += _SCREEN_SELECTOR_CALLBACK_SNIPPET
    try:
        script_knob.setValue(new_script)
    except Exception:
        pass


def _ensure_screen_selector(group: object) -> None:
    """Add/update the Write tab pulldown for selecting the local screen."""

    screens = gsv_utils.get_list_options("__default__.screens")
    knobs = getattr(group, "knobs")()
    selector = knobs.get(_SCREEN_SELECTOR_KNOB)
    if not screens:
        if selector is not None:
            try:
                selector.setVisible(False)
            except Exception:
                pass
        return

    if selector is None:
        selector = nuke.Enumeration_Knob(_SCREEN_SELECTOR_KNOB, "Screen", screens)  # type: ignore[attr-defined]
        selector.setTooltip("Select which screen this VariableGroup should render with. Only this node is affected.")
        group.addKnob(selector)
        knobs[_SCREEN_SELECTOR_KNOB] = selector
    else:
        try:
            selector.setValues(screens)
        except Exception:
            return
        selector.setVisible(True)

    current = _get_group_screen(group)
    if not current or current not in screens:
        fallback = gsv_utils.get_current_screen() or (screens[0] if screens else None)
        if fallback:
            current = fallback
            _set_group_screen(group, current)

    try:
        if current:
            selector.setValue(current)
    except Exception:
        pass

    _install_screen_selector_callback(group)


@dataclass(frozen=True)
class WritePromoteConfig:
    """Configuration for selecting Write knobs to expose.

    - default_knobs: used when wrapper does not provide an override list
    - per_filetype_knobs: optional overrides based on the Write's `file_type`
    - write_tab_label: label for the tab where links are added
    - show_scope_on_label: if True, wrapper label shows current GSV
    - tile_color: optional tile color to set on the wrapper
    """

    default_knobs: List[str]
    per_filetype_knobs: Optional[Dict[str, List[str]]] = None
    write_tab_label: str = "Write"
    show_scope_on_label: bool = True
    tile_color: Optional[int] = 4290838783


class WriteKnobPromoter:
    """Encapsulates logic to expose internal Write knobs on a VariableGroup."""

    def __init__(self, cfg: WritePromoteConfig) -> None:
        """Store the configuration for later use."""

        self.cfg = cfg

    def _group_whitelist(self, group: object) -> Optional[List[str]]:
        """Read selected write knobs from the wrapper's Boolean whitelist."""

        try:
            knobs_map = getattr(group, "knobs")()
        except Exception:
            return None

        selected: List[str] = []
        any_toggle = False
        for name, knob in list(knobs_map.items()):
            if not name.startswith(_WHITELIST_TOGGLE_PREFIX):
                continue
            any_toggle = True
            try:
                enabled = bool(knob.value())
            except Exception:
                enabled = False
            original = _original_name_from_toggle(name, knob)
            if enabled:
                selected.append(original)
        if any_toggle:
            return selected
        return None

    def _knob_list_for(self, group: object, write_node: object) -> List[str]:
        """Choose knob list based on wrapper override or file_type mapping."""

        override = self._group_whitelist(group)
        if override:
            return override
        try:
            ft = write_node["file_type"].value()
        except Exception:
            ft = None
        if ft and self.cfg.per_filetype_knobs and ft in self.cfg.per_filetype_knobs:
            return self.cfg.per_filetype_knobs[ft]
        return list(self.cfg.default_knobs)

    def expose(self, group: object, write_node: object) -> int:
        """Expose selected knobs onto the VariableGroup under the Write tab.

        Also ensures the BCN management tab exists. Returns the number of links added.
        """

        knob_order = self._knob_list_for(group, write_node)
        _ensure_management_tab(group, knob_order, write_node)
        _ensure_tab(group, self.cfg.write_tab_label, self.cfg.write_tab_label)
        _activate_tab(group, self.cfg.write_tab_label)
        _ensure_screen_selector(group)

        added = 0
        for name in knob_order:
            label = None
            try:
                k = write_node[name]
                label = k.label() if hasattr(k, "label") else name
            except Exception:
                label = name
            if _add_link_knob(group, write_node, name, label):
                added += 1

        if self.cfg.show_scope_on_label:
            try:
                group["label"].setValue("[value gsv]")
            except Exception:
                pass
        if self.cfg.tile_color is not None:
            try:
                group["tile_color"].setValue(self.cfg.tile_color)
            except Exception:
                pass
        return added


def _find_internal_node(group: object, prefer_publish_instance: bool = False, original_name: Optional[str] = None) -> Optional[object]:
    """Find the internal node to promote from, preferring Write or publishable.

    When `prefer_publish_instance` is True, a node exposing `publish_instance`
    inside the group is preferred over a plain Write node.
    """

    try:
        with group:
            # Prefer lookup by original name when provided
            if original_name:
                try:
                    named = nuke.toNode(original_name)
                    if named is not None:
                        return named
                except Exception:
                    pass
            nodes = list(nuke.allNodes(recurse=False))  # type: ignore[attr-defined]
            if prefer_publish_instance:
                for node in nodes:
                    try:
                        if "publish_instance" in node.knobs():
                            return node
                    except Exception:
                        continue
            for node in nodes:
                try:
                    if node.Class() == "Write":
                        return node
                except Exception:
                    continue
            return nodes[0] if nodes else None
    except Exception:
        return None


def _collapse_into_variable_group(node: object) -> Optional[object]:
    """Collapse the given node into a new VariableGroup and return it."""

    try:
        previous_selection = list(nuke.selectedNodes())  # type: ignore[attr-defined]
    except Exception:
        previous_selection = []
    try:
        for other in previous_selection:
            try:
                other.setSelected(False)
            except Exception:
                pass
        node.setSelected(True)
        vg = nuke.collapseToVariableGroup()  # type: ignore[attr-defined]
    except Exception:
        vg = None
    finally:
        try:
            if vg is not None:
                vg.setSelected(True)
            else:
                for other in previous_selection:
                    try:
                        other.setSelected(True)
                    except Exception:
                        pass
        except Exception:
            pass
    return vg


def refresh_variable_group_links(group: Optional[object] = None) -> int:
    """Refresh the wrapper's exposed links based on its current whitelist.

    If `group` is None, the currently selected node is used if it is a VariableGroup.
    Returns the number of links added.
    """

    g = group
    if g is None:
        try:
            g = nuke.thisNode()  # type: ignore[attr-defined]
        except Exception:
            try:
                g = nuke.selectedNode()  # type: ignore[attr-defined]
            except Exception:
                return 0
    # Sanitize any legacy script prefixes before proceeding
    try:
        _sanitize_group_knob_scripts(g)
    except Exception:
        pass
    try:
        klass = g.Class()
    except Exception:
        return 0
    if klass != "VariableGroup":
        return 0

    target = _find_internal_node(g)
    if target is None:
        return 0
    promoter = WriteKnobPromoter(WritePromoteConfig(default_knobs=_DEFAULT_WRITE_KNOBS))
    return promoter.expose(g, target)

    # Removed legacy introspection-based promotion


    # Replaced by simplified _find_internal_node above


    # Replaced by simplified _collapse_into_variable_group above


def _on_screen_selector_changed(group: Optional[object], selection) -> None:
    """Callback for the Write tab screen selector to update the local GSV."""

    if group is None:
        return
    value = selection
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, (int, float)):
        try:
            knob = group[_SCREEN_SELECTOR_KNOB]
            if hasattr(knob, "values"):
                options = knob.values()
                idx = int(value)
                if 0 <= idx < len(options):
                    value = options[idx]
        except Exception:
            value = None
    if not value:
        try:
            knob = group[_SCREEN_SELECTOR_KNOB]
            value = knob.value()
        except Exception:
            value = None
    if value:
        _set_group_screen(group, str(value))


def encapsulate_write_with_variable_group(node: Optional[object] = None) -> Optional[object]:
    """Wrap a Write or publishable Group inside a VariableGroup and expose knobs.

    The wrapper gains:
    - A Write tab with selected Link_Knobs
    - A "BCN Wrapper" tab with checkbox whitelist controls and a Refresh button
    """

    target = node
    if target is None:
        try:
            target = nuke.selectedNode()  # type: ignore[attr-defined]
        except Exception:
            nuke.message("Select a Write node first")
            return None

    prefer_publish = False

    try:
        node_class = target.Class()
    except Exception:
        nuke.message("Unable to determine node class")
        return None

    try:
        has_publish_knob = "publish_instance" in target.knobs()
    except Exception:
        has_publish_knob = False

    if node_class != "Write" and not (node_class == "Group" and has_publish_knob):
        nuke.message("Select a Write node or a Group with a publish_instance knob")
        return None

    if node_class == "Group" and has_publish_knob:
        prefer_publish = True

    # Capture the original name to keep clarity inside the wrapper.
    original_name = "Write"
    try:
        name_attr = getattr(target, "name", None)
        if callable(name_attr):
            original_name = name_attr()
        elif name_attr:
            original_name = str(name_attr)
    except Exception:
        pass

    undo = getattr(nuke, "Undo", None)
    if undo is not None:
        try:
            undo.begin("Encapsulate Write in VariableGroup")
        except Exception:
            undo = None

    # Sanitize any legacy script prefixes on the source node before collapsing
    try:
        _sanitize_knob_scripts(target)
    except Exception:
        pass

    try:
        group = _collapse_into_variable_group(target)
        if group is None:
            return None

        try:
            group.setName(f"{original_name}_VG")
        except Exception:
            pass

        # Sanitize any legacy script prefixes to avoid SyntaxError before lookups
        try:
            _sanitize_group_knob_scripts(group)
        except Exception:
            pass

        promote_target = _find_internal_node(group, prefer_publish_instance=prefer_publish, original_name=original_name)
        if promote_target is None:
            nuke.message("The VariableGroup does not contain the expected node")
            return group

        # Ensure the internal node keeps its original name for clarity.
        try:
            promote_target.setName(original_name)
        except Exception:
            pass

        promoter = WriteKnobPromoter(WritePromoteConfig(default_knobs=_DEFAULT_WRITE_KNOBS))
        promoter.expose(group, promote_target)

        # Show the active variable scope directly on the wrapper label.
        try:
            label_knob = group["label"]
            label_knob.setValue("[value gsv]")
        except Exception:
            pass
        
        try:
            tile_color_knob = group["tile_color"]
            tile_color_knob.setValue(4290838783)
        except Exception:
            pass

        try:
            group.showControlPanel()
        except Exception:
            pass

        return group
    finally:
        if undo is not None:
            try:
                undo.end()
            except Exception:
                pass


__all__ = [
    "encapsulate_write_with_variable_group",
    "refresh_variable_group_links",
]
