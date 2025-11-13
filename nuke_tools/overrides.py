"""Helpers to create per-screen overrides using GSVs and expressions.

This aligns with the corrected mental model:
  - A global List selector lives at `__default__.screens`.
  - Each screen has a Variable Set at the root, e.g. `Sphere`, `TSQ_Duffy`.
  - Values are referenced in strings via `%Set.Var` (fixed set), while
    dynamic per-screen numeric knobs can use short Python expressions.

Avoid generic callbacks where possible. Prefer expressions and
VariableSwitch/Link nodes. Where knob values must change based on the
currently selected screen, inject a compact Python expression that reads
`__default__.screens` and fetches the field from the selected set.
"""

from typing import Optional

try:
    import nuke  # type: ignore
except Exception:  # pragma: no cover
    nuke = None  # type: ignore


def set_knob_expression_from_gsv(node: "nuke.Node", knob_name: str, gsv_path: str) -> None:  # type: ignore[name-defined]
    """Inject a python expression to read a value from a GSV path.

    Example expression: python {nuke.root()['gsv'].getGsvValue('Set.var')}
    """

    if nuke is None or node is None:
        return
    try:
        expr = f"python {{nuke.root()['gsv'].getGsvValue('{gsv_path}')}}"
        node[knob_name].setExpression(expr)
    except Exception:
        pass


def set_knob_expression_for_screen_field(node: "nuke.Node", knob_name: str, field: str) -> None:  # type: ignore[name-defined]
    """Inject a Python expression that reads `<field>` from the selected screen.

    This uses the global selector at `__default__.screens` to resolve the
    active screen name, then reads `ActiveSet.<field>` from the root GSV.
    Example injected expression for field "width":
      python {g=nuke.root()['gsv']; s=g.getGsvValue('__default__.screens'); g.getGsvValue(s + '.width')}
    """

    if nuke is None or node is None:
        return
    try:
        expr = (
            "python {g=nuke.root()['gsv']; s=g.getGsvValue('__default__.screens'); "
            f"g.getGsvValue(s + '.{field}')}"  # field is literal in the expression
        )
        node[knob_name].setExpression(expr)
    except Exception:
        pass


def on_screen_changed(callback) -> Optional[object]:
    """Attach a handler for when `__default__.screens` changes, if supported.

    Uses `nuke.callbacks.onGsvSetChanged` when available; returns the handler
    token/object if applicable; otherwise None.
    """

    if nuke is None:
        return None

    cb = getattr(nuke, "callbacks", None)
    if cb is None:
        return None

    handler = None
    try:
        # Prefer the specific GSV change callback if present
        if hasattr(cb, "onGsvSetChanged"):
            handler = cb.onGsvSetChanged(callback)  # type: ignore[attr-defined]
            return handler
    except Exception:
        # Fall back to no registration; callers can decide alternative strategies
        return None
    return None


__all__ = [
    "set_knob_expression_from_gsv",
    "set_knob_expression_for_screen_field",
    "on_screen_changed",
]


