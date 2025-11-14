"""Thin utilities around Nuke's GSV API to keep code readable.

All functions are defensive and return early when Nuke is not available to
keep the module import-safe outside Nuke.
"""

from typing import Iterable, List, Optional, Sequence, Dict, Any, Tuple

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


def remove_variant(variant_name: str) -> None:
    """Remove the entire `__default__.<variant>` entry if it exists."""

    path = _variant_path(variant_name)
    if path is None:
        return

    gsv = get_root_gsv_knob()
    if gsv is None:
        return

    try:
        remove = getattr(gsv, "removeGsv", None)
        if callable(remove):
            remove(path)  # type: ignore[arg-type]
    except Exception:
        pass


def _variant_path(variant_name: str) -> Optional[str]:
    """Return the canonical GSV path for a variant name."""

    variant = (variant_name or "").strip()
    if not variant:
        return None
    return f"__default__.{variant}"


def _normalized_options(options: Sequence[str]) -> List[str]:
    """Return a deduplicated list of clean option strings (order preserved)."""

    clean: List[str] = []
    seen = set()
    for opt in options:
        text = str(opt).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        clean.append(text)
    return clean


def ensure_variant_list(
    variant_name: str, options: Sequence[str], default_option: Optional[str] = None
) -> None:
    """Ensure a list-type variant (e.g. `screens`, `version`) exists with options.

    Parameters
    ----------
    variant_name:
        The bare variant key, e.g. ``"screens"`` (mapped to ``__default__.screens``).
    options:
        Iterable of option names; duplicates and empty strings are removed.
    default_option:
        Choice that should be selected; falls back to the first option.
    """

    path = _variant_path(variant_name)
    if path is None:
        return

    clean_options = _normalized_options(options)
    if not clean_options:
        return

    default = default_option if default_option in clean_options else clean_options[0]

    try:
        set_value(path, default)
    except Exception:
        pass

    ensure_list_datatype(path)
    set_list_options(path, clean_options)
    try:
        set_favorite(path, True)
    except Exception:
        pass


def get_variant_options(variant_name: str) -> List[str]:
    """Return list options for the requested variant name."""

    path = _variant_path(variant_name)
    if path is None:
        return []
    return get_list_options(path)


def set_variant_value(variant_name: str, value: str) -> None:
    """Set the selected option for a list-type variant."""

    path = _variant_path(variant_name)
    if path is None:
        return
    set_value(path, value)


def get_variant_value(variant_name: str) -> Optional[str]:
    """Return the current selection for a list-type variant."""

    path = _variant_path(variant_name)
    if path is None:
        return None
    return get_value(path)


def discover_list_variants() -> Dict[str, List[str]]:
    """Return a mapping of variant name -> options for all list-type entries."""

    variants: Dict[str, List[str]] = {}
    root_value = get_knob_value()
    default_set = root_value.get("__default__", {})
    for raw_name in default_set.keys():
        name = str(raw_name)
        path = _variant_path(name)
        if path is None:
            continue
        options = get_list_options(path)
        if options:
            variants[name] = options
    return variants


def get_all_list_variants_with_current() -> Dict[str, Dict[str, Any]]:
    """Return metadata for each list-type variant (options + current value)."""

    variants: Dict[str, Dict[str, Any]] = {}
    discovered = discover_list_variants()
    for name, options in discovered.items():
        current = get_variant_value(name)
        if not current and options:
            current = options[0]
        variants[name] = {"options": options, "current": current}
    return variants


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
    """Backwards-compatible wrapper for `ensure_variant_list(\"screens\", ...)`."""

    ensure_variant_list("screens", screens, default_screen)


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
    """Ensure there is a GSV set for each screen name (legacy helper)."""

    ensure_option_sets(screens)


def ensure_option_sets(option_names: Sequence[str]) -> None:
    """Ensure there is a GSV set for every provided option name."""

    for name in _normalized_options(option_names):
        try:
            add_set(name)
        except Exception:
            pass


def get_current_screen() -> Optional[str]:
    """Return the currently selected screen (legacy helper)."""

    return get_variant_value("screens")


def get_value_for_current_screen(key: str) -> Optional[str]:
    """Return the value of `<key>` for the currently selected screen.

    Example: if `__default__.screens` == "Sphere", returns value at
    `Sphere.<key>`.
    """

    current = get_current_screen()
    if not current:
        return None
    return get_value(f"{current}.{key}")


