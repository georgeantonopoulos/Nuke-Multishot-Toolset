"""Thin utilities around Nuke's GSV API to keep code readable.

All functions are defensive and return early when Nuke is not available to
keep the module import-safe outside Nuke.
"""

from typing import Iterable, List, Optional, Sequence, Dict, Any

try:
    import nuke  # type: ignore
except Exception:  # pragma: no cover - allow importing outside Nuke
    nuke = None  # type: ignore


def get_root_gsv_knob():
    """Return the Root GSV knob (`nuke.Gsv_Knob`) or None if unavailable."""

    if nuke is None:
        return None
    try:
        return nuke.root()["gsv"]
    except Exception:
        return None


def ensure_list_datatype(path: str) -> None:
    """Ensure the GSV at `path` is of type List.

    If unavailable, this is a no-op.
    """

    gsv = get_root_gsv_knob()
    if gsv is None:
        return
    try:
        # Use fully qualified paths that include the set, e.g. "__default__.screen"
        gsv.setDataType(path, nuke.gsv.DataType.List)  # type: ignore[attr-defined]
    except Exception:
        pass


def set_list_options(path: str, options: Sequence[str]) -> None:
    """Set list options for a List-type GSV at `path`. No-op on failure."""

    gsv = get_root_gsv_knob()
    if gsv is None:
        return
    try:
        gsv.setListOptions(path, list(options))
    except Exception:
        pass


def get_list_options(path: str) -> List[str]:
    """Get list options for a List-type GSV at `path`. Returns empty on error."""

    gsv = get_root_gsv_knob()
    if gsv is None:
        return []
    try:
        opts = gsv.getListOptions(path)
        return list(opts) if isinstance(opts, Iterable) else []
    except Exception:
        return []


def set_value(path: str, value: str) -> None:
    """Set the GSV value at `path`. No-op on failure."""

    gsv = get_root_gsv_knob()
    if gsv is None:
        return
    try:
        gsv.setGsvValue(path, value)
    except Exception:
        pass


def set_favorite(path: str, is_favorite: bool = True) -> None:
    """Mark a GSV at `path` as a favorite so it appears prominently in UI.

    No-op on failure or when Nuke is unavailable.
    """

    gsv = get_root_gsv_knob()
    if gsv is None:
        return
    try:
        gsv.setFavorite(path, bool(is_favorite))  # type: ignore[attr-defined]
    except Exception:
        pass


def get_value(path: str) -> Optional[str]:
    """Get the GSV value at `path`. Returns None on error."""

    gsv = get_root_gsv_knob()
    if gsv is None:
        return None
    try:
        return gsv.getGsvValue(path)
    except Exception:
        return None


def add_set(set_name: str) -> None:
    """Ensure a GSV set exists at the root level (e.g. "Screens").

    Uses `gsv.addGsvSet(set_name)`. Safe to call repeatedly.
    """

    gsv = get_root_gsv_knob()
    if gsv is None:
        return
    try:
        gsv.addGsvSet(set_name)
    except Exception:
        # If it already exists or the API rejects, ignore
        pass


def get_knob_value() -> Dict[str, Dict[str, str]]:
    """Return the entire GSV mapping as a nested dict of sets -> variables.

    Structure: { '__default__': { 'var': 'value', ... }, 'SetName': { ... } }
    Returns an empty mapping on error.
    """

    gsv = get_root_gsv_knob()
    if gsv is None:
        return {}
    try:
        val = gsv.value()
        # Defensive cast
        if isinstance(val, dict):
            return {str(k): dict(v) for k, v in val.items() if isinstance(v, dict)}
        return {}
    except Exception:
        return {}


def set_knob_value(value_map: Dict[str, Dict[str, Any]]) -> None:
    """Set the entire GSV mapping in one call via `gsv.setValue(value_map)`.

    Values are coerced to strings by Nuke where appropriate.
    """

    gsv = get_root_gsv_knob()
    if gsv is None:
        return
    try:
        gsv.setValue(value_map)
    except Exception:
        pass


def merge_root_value(updates: Dict[str, Dict[str, Any]]) -> None:
    """Deep-merge `updates` into the root GSV mapping and write back with setValue().

    Example `updates`:
        { '__default__': { 'screen': 'Moxy' }, 'Screens': { 'names_csv': 'Moxy,Godzilla' } }
    """

    current = get_knob_value()
    # Merge updates
    for set_name, vars_map in updates.items():
        if not isinstance(vars_map, dict):
            continue
        dst = current.setdefault(set_name, {})
        for key, val in vars_map.items():
            dst[key] = val
    set_knob_value(current)


def ensure_screen_list(screens: Sequence[str], default_screen: Optional[str] = None) -> None:
    """Ensure `__default__.screens` exists, is a List, and has given options.

    Parameters:
      - screens: unique screen names
      - default_screen: initial selection; falls back to first option
    """

    # Guard: if provided default is not among options, fall back to first option
    if (not default_screen or (default_screen not in screens)) and screens:
        default_screen = screens[0]

    # Create the variable first so subsequent type/option calls can succeed
    if default_screen:
        try:
            set_value("__default__.screens", default_screen)
        except Exception:
            pass

    # Ensure list type and options on the newly created variable
    # IMPORTANT: Do not call gsv.setValue/merge_root_value here, as it
    # would reset the variable type back to Text. Use the typed API only.
    ensure_list_datatype("__default__.screens")
    set_list_options("__default__.screens", screens)
    # Ensure visibility in Variables panel by marking as favorite
    try:
        set_favorite("__default__.screens", True)
    except Exception:
        pass


def create_variable_group(name: str):
    """Create a VariableGroup node with the given name, if possible.

    Returns the group node or None.
    """

    if nuke is None:
        return None
    try:
        return nuke.nodes.VariableGroup(name=name)
    except Exception:
        return None


def ensure_screen_sets(screens: Sequence[str]) -> None:
    """Ensure there is a GSV set for each screen name.

    This follows the mental model where each screen is a Variable Set at root
    (e.g. `Sphere`, `TSQ_Duffy`). Values can then be referenced as
    `%Sphere.width` or `%TSQ_Duffy.output_root` in string knobs.
    """

    for name in screens:
        try:
            if name:
                add_set(str(name))
        except Exception:
            # Non-fatal; continue with the rest
            pass


def get_current_screen() -> Optional[str]:
    """Return the currently selected screen from `__default__.screens`.

    Returns None if unavailable.
    """

    try:
        return get_value("__default__.screens")
    except Exception:
        return None


def get_value_for_current_screen(key: str) -> Optional[str]:
    """Return the value of `<key>` for the currently selected screen.

    Example: if `__default__.screens` == "Sphere", returns value at
    `Sphere.<key>`.
    """

    current = get_current_screen()
    if not current:
        return None
    try:
        return get_value(f"{current}.{key}")
    except Exception:
        return None


