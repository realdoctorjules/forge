"""The P0 hello-world device: a parametric project enclosure.

This is a hand-written parametric part. In P-B (only if SPIKE-1 passes) the
LLM will author modules shaped exactly like this one. Keeping the cadquery
import *inside* build() means the backend can read PARAMS cheaply without
loading the OCCT kernel, and the import-allowlist still sees it as an
allowed import when scanning generated parts.

build(params, checkpoint) must call checkpoint("<op>") immediately before each
kernel operation so the isolation layer can attribute a native crash/timeout to
a specific operation.
"""

PART_NAME = "hello_enclosure"

# Named, bounded parameters. min/max double as the slider range AND the
# topology-preserving safe range probed in P-B.
PARAMS = {
    "width":  {"value": 60.0, "min": 30.0, "max": 120.0, "step": 1.0,  "unit": "mm", "label": "Width (X)"},
    "depth":  {"value": 40.0, "min": 25.0, "max": 100.0, "step": 1.0,  "unit": "mm", "label": "Depth (Y)"},
    "height": {"value": 25.0, "min": 12.0, "max": 60.0,  "step": 1.0,  "unit": "mm", "label": "Height (Z)"},
    "wall":   {"value": 2.0,  "min": 1.2,  "max": 4.0,   "step": 0.1,  "unit": "mm", "label": "Wall thickness"},
    "fillet": {"value": 3.0,  "min": 0.0,  "max": 8.0,   "step": 0.5,  "unit": "mm", "label": "Corner fillet"},
}

# Default print material assumption used for the mass estimate (overridable later).
MATERIAL = {"name": "PLA", "density_g_cm3": 1.24}


def defaults() -> dict:
    return {k: v["value"] for k, v in PARAMS.items()}


def clamp(params: dict) -> dict:
    out = {}
    for k, spec in PARAMS.items():
        v = float(params.get(k, spec["value"]))
        out[k] = max(spec["min"], min(spec["max"], v))
    return out


def build(params, checkpoint):
    import cadquery as cq

    p = clamp(params)
    w, d, h = p["width"], p["depth"], p["height"]
    wall, fil = p["wall"], p["fillet"]

    from ._util import safe_fillet, safe_shell
    checkpoint("box")
    body = cq.Workplane("XY").box(w, d, h)

    checkpoint("fillet_vertical_edges")
    body = safe_fillet(body, "|Z", min(fil, w / 2 - 0.5, d / 2 - 0.5))

    checkpoint("shell_open_top")
    body = safe_shell(body, ">Z", wall)

    return body
