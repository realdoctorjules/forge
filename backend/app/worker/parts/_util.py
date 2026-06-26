"""Shared helpers for parametric device archetypes (no cadquery import here)."""
from __future__ import annotations


def defaults(PARAMS: dict) -> dict:
    return {k: v["value"] for k, v in PARAMS.items()}


def safe_fillet(body, edge_selector: str, radius: float):
    """Fillet, but skip gracefully if OCCT can't (radius too big for the edge)."""
    if radius is None or radius <= 0:
        return body
    try:
        return body.edges(edge_selector).fillet(radius)
    except Exception:  # noqa: BLE001 — OCCT Standard_Failure etc.
        return body


def safe_shell(body, face_selector: str, wall: float):
    """Shell (hollow) a face, retrying thinner walls; fall back to the solid if
    OCCT fails entirely. Prevents silent build failures from wall/fillet combos."""
    for w in (wall, wall * 0.6, max(wall * 0.4, 1.0)):
        try:
            return body.faces(face_selector).shell(-w)
        except Exception:  # noqa: BLE001
            continue
    return body


def clamp_params(PARAMS: dict, params: dict) -> dict:
    out = {}
    for k, spec in PARAMS.items():
        v = float(params.get(k, spec["value"]))
        v = max(spec["min"], min(spec["max"], v))
        if spec.get("integer"):
            v = round(v)
        out[k] = v
    return out
