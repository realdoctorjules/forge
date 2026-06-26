"""C-shaped cable / cord clip that snaps around a cable."""
from ._util import clamp_params, defaults as _defaults

PART_NAME = "cable_clip"
PARAMS = {
    "cable_d":   {"value": 8.0,  "min": 3.0,  "max": 30.0, "step": 0.5, "unit": "mm", "label": "Cable diameter"},
    "thickness": {"value": 2.5,  "min": 1.5,  "max": 5.0,  "step": 0.1, "unit": "mm", "label": "Wall thickness"},
    "width":     {"value": 10.0, "min": 5.0,  "max": 30.0, "step": 1.0, "unit": "mm", "label": "Clip width"},
    "gap":       {"value": 5.0,  "min": 2.0,  "max": 20.0, "step": 0.5, "unit": "mm", "label": "Opening gap"},
}
DEFAULT_MATERIAL = "TPU"
STANDARD_PARTS: list = []


def defaults():
    return _defaults(PARAMS)


def clamp(params):
    return clamp_params(PARAMS, params)


def build(params, checkpoint):
    import cadquery as cq
    p = clamp_params(PARAMS, params)
    cable, t, w, gap = p["cable_d"], p["thickness"], p["width"], p["gap"]
    outer_r = cable / 2.0 + t
    checkpoint("ring")
    body = cq.Workplane("XY").circle(outer_r).extrude(w)
    checkpoint("bore")
    body = body.faces(">Z").workplane().hole(cable)
    checkpoint("opening")
    gap = min(gap, cable + t)  # keep the opening sane
    cut = cq.Workplane("XY").box(outer_r * 2, gap, w).translate((outer_r, 0, w / 2.0))
    body = body.cut(cut)
    return body
