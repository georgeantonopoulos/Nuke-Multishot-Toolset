"""Minimal helpers for inserting VariableGroups ahead of Write nodes.

The previous implementation collapsed nodes and mirrored every Write knob.
For the current workflow we only need a lightweight helper that:
  - inserts a VariableGroup upstream of the selected Write/Group
  - rewires the main input so existing streams continue to the new group
  - sets a readable label (`[value gsv]`) so artists can see the scope
  - forces the group's `__default__.screens` value to match the panel's pick
"""
from typing import Optional

try:  # pragma: no cover - Nuke runtime provides the real module
    import nuke  # type: ignore
except Exception:  # pragma: no cover
    nuke = None  # type: ignore

try:
    from . import gsv_utils  # type: ignore
except Exception:  # pragma: no cover - fallback when loaded as loose modules
    import gsv_utils  # type: ignore

try:
    from . import screens_manager  # type: ignore
except Exception:  # pragma: no cover
    try:
        import screens_manager  # type: ignore
    except Exception:  # pragma: no cover
        screens_manager = None  # type: ignore


def _log_exception(context: str, exc: Exception) -> None:
    """Log exceptions to the Nuke script editor or stdout."""

    message = f"[render_hooks] {context}: {exc}"
    try:
        if nuke is not None and hasattr(nuke, "tprint"):
            nuke.tprint(message)  # type: ignore[attr-defined]
        else:
            print(message)  # noqa: T201
    except Exception:
        # Fall back to stdout if the Nuke print helper fails
        print(message)  # noqa: T201


def _selected_panel_screen() -> Optional[str]:
    """Return the current screen selected in the Screens Manager UI."""

    panel_module = screens_manager
    if panel_module is None:
        return None
    panel_cls = getattr(panel_module, "ScreensManagerPanel", None)
    inst = getattr(panel_cls, "instance", None) if panel_cls else None
    combo = getattr(inst, "default_combo", None) if inst is not None else None
    if combo is None:
        return None
    try:
        text = combo.currentText()
    except Exception:
        return None
    text = (text or "").strip()
    return text or None


def _current_screen_fallback() -> Optional[str]:
    """Best-effort screen selection (panel -> current value -> first option)."""

    screen = _selected_panel_screen()
    if screen:
        return screen
    screen = gsv_utils.get_current_screen()
    if screen:
        return screen
    options = gsv_utils.get_list_options("__default__.screens")
    return options[0] if options else None


def _node_name(node: object) -> str:
    try:
        name_attr = getattr(node, "name", None)
        if callable(name_attr):
            return str(name_attr())
        if name_attr:
            return str(name_attr)
    except Exception:
        pass
    return "Node"


def _position_group(group: object, target: object) -> None:
    """Place the new group to the left of the target node (best-effort)."""

    try:
        tx = int(target["xpos"].value())
        ty = int(target["ypos"].value())
        group["xpos"].setValue(tx)

        upstream = None
        try:
            upstream = target.input(0)
        except Exception:
            upstream = None

        if upstream is not None:
            try:
                uy = int(upstream["ypos"].value())
                group["ypos"].setValue(int((ty + uy) / 2))
                return
            except Exception:
                pass

        group["ypos"].setValue(ty)
    except Exception:
        pass


def _rewire_primary_input(group: object, target: object) -> None:
    """Insert the VariableGroup between the target and its primary input."""

    upstream = None
    try:
        upstream = target.input(0)
    except Exception:
        upstream = None
    try:
        group.setInput(0, upstream)
    except Exception:
        pass
    try:
        target.setInput(0, group)
    except Exception:
        pass


def _ensure_group_terminals(group: object) -> None:
    """Ensure the VariableGroup contains Input/Output nodes for connectivity."""

    if nuke is None:
        return
    try:
        # Explicitly enter the group's context; VariableGroup may not support a context manager
        group.begin()
        try:
            nodes = list(nuke.allNodes())
            input_nodes = [node for node in nodes if node.Class() == "Input"]
            output_nodes = [node for node in nodes if node.Class() == "Output"]

            if input_nodes:
                inp = input_nodes[0]
            else:
                try:
                    # create Input inside the group
                    inp = nuke.nodes.Input()
                except Exception as exc:
                    _log_exception("create Input node", exc)
                    return

            try:
                inp.setName("Input1")
            except Exception as exc:
                _log_exception("rename Input node", exc)

            if output_nodes:
                out = output_nodes[0]
            else:
                try:
                    # create Output inside the group
                    out = nuke.nodes.Output()
                except Exception as exc:
                    _log_exception("create Output node", exc)
                    return

            try:
                out.setName("Output1")
            except Exception as exc:
                _log_exception("rename Output node", exc)

            try:
                out.setInput(0, inp)
            except Exception as exc:
                _log_exception("connect Output to Input", exc)
        finally:
            try:
                group.end()  # type: ignore[attr-defined]
            except Exception as exc:
                _log_exception("group.end()", exc)
    except Exception as exc:
        _log_exception("ensure_group_terminals(group.begin)", exc)


def _set_group_label(group: object) -> None:
    try:
        group["label"].setValue("[value gsv]")
    except Exception:
        pass


def _set_group_screen(group: object) -> None:
    """Force the group's scope to match the panel (or fallback selection)."""

    screen = _current_screen_fallback()
    if not screen:
        return
    try:
        group["gsv"].setGsvValue("__default__.screens", screen)
    except Exception:
        pass


def _set_group_tile_color(group: object) -> None:
    """Apply a distinctive tile color to VariableGroups created via the wrap helper."""

    try:
        group["tile_color"].setValue(3383053311)
    except Exception:
        pass


def _supported_target(node: object) -> bool:
    try:
        cls = node.Class()
    except Exception:
        return False
    return cls in {"Write", "Group"}


def _selected_target(node: Optional[object]) -> Optional[object]:
    if node is not None:
        return node
    if nuke is None:
        return None
    try:
        return nuke.selectedNode()  # type: ignore[attr-defined]
    except Exception:
        nuke.message("Select a Write node or Group first")
        return None


def encapsulate_write_with_variable_group(node: Optional[object] = None) -> Optional[object]:
    """Insert a VariableGroup upstream of the selected Write/Group."""

    if nuke is None:
        return None

    target = _selected_target(node)
    if target is None:
        return None
    if not _supported_target(target):
        nuke.message("Select a Write node or Group")
        return None

    undo = getattr(nuke, "Undo", None)
    if undo is not None:
        try:
            undo.begin("Insert VariableGroup for screens")
        except Exception:
            undo = None

    try:
        try:
            group = nuke.nodes.VariableGroup()
        except Exception:
            nuke.message("Unable to create VariableGroup node")
            return None

        try:
            group.setName(nuke.uniqueName(f"{_node_name(target)}_VG"))
        except Exception:
            pass

        _ensure_group_terminals(group)
        _position_group(group, target)
        _rewire_primary_input(group, target)
        _set_group_label(group)
        _set_group_screen(group)
        _set_group_tile_color(group)

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


__all__ = ["encapsulate_write_with_variable_group"]
