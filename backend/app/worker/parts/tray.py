"""Compartment tray / organizer / pill box: a grid of pockets."""
from ._util import clamp_params, defaults as _defaults

PART_NAME = "tray"
PARAMS = {
    "width":  {"value": 90.0, "min": 40.0, "max": 180.0, "step": 1.0, "unit": "mm", "label": "Width (X)"},
    "depth":  {"value": 60.0, "min": 40.0, "max": 180.0, "step": 1.0, "unit": "mm", "label": "Depth (Y)"},
    "height": {"value": 25.0, "min": 10.0, "max": 60.0,  "step": 1.0, "unit": "mm", "label": "Height (Z)"},
    "wall":   {"value": 2.0,  "min": 1.2,  "max": 4.0,   "step": 0.1, "unit": "mm", "label": "Wall thickness"},
    "cols":   {"value": 4,    "min": 1,    "max": 8,     "step": 1,   "unit": "",   "label": "Columns", "integer": True},
    "rows":   {"value": 2,    "min": 1,    "max": 6,     "step": 1,   "unit": "",   "label": "Rows", "integer": True},
}
DEFAULT_MATERIAL = "PLA"
STANDARD_PARTS: list = []


def defaults():
    return _defaults(PARAMS)


def clamp(params):
    return clamp_params(PARAMS, params)


def build(params, checkpoint):
    import cadquery as cq
    p = clamp_params(PARAMS, params)
    w, d, h, wall = p["width"], p["depth"], p["height"], p["wall"]
    cols, rows = int(p["cols"]), int(p["rows"])

    checkpoint("box")
    body = cq.Workplane("XY").box(w, d, h)

    from ._util import safe_fillet
    checkpoint("fillet")
    body = safe_fillet(body, "|Z", min(2.5, w / 2 - 1, d / 2 - 1))

    checkpoint("pockets")
    cellw = (w - 2 * wall - (cols - 1) * wall) / cols
    celld = (d - 2 * wall - (rows - 1) * wall) / rows
    if cellw > 1 and celld > 1:
        body = (
            body.faces(">Z").workplane()
            .rarray(cellw + wall, celld + wall, cols, rows, center=True)
            .rect(cellw, celld)
            .cutBlind(-(h - wall))
        )
    return body
