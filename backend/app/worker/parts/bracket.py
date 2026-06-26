"""Mounting bracket / plate with corner screw holes."""
from ._util import clamp_params, defaults as _defaults

PART_NAME = "bracket"
PARAMS = {
    "width":     {"value": 70.0, "min": 40.0, "max": 180.0, "step": 1.0, "unit": "mm", "label": "Width (X)"},
    "depth":     {"value": 45.0, "min": 30.0, "max": 160.0, "step": 1.0, "unit": "mm", "label": "Depth (Y)"},
    "thickness": {"value": 4.0,  "min": 2.0,  "max": 12.0,  "step": 0.5, "unit": "mm", "label": "Thickness"},
    "hole_d":    {"value": 4.2,  "min": 2.0,  "max": 10.0,  "step": 0.1, "unit": "mm", "label": "Hole diameter"},
    "margin":    {"value": 8.0,  "min": 5.0,  "max": 25.0,  "step": 0.5, "unit": "mm", "label": "Hole inset"},
}
DEFAULT_MATERIAL = "PLA"
STANDARD_PARTS = [{"name": "M4 machine screw", "qty": 4, "unit_cost": 0.12}]


def defaults():
    return _defaults(PARAMS)


def clamp(params):
    return clamp_params(PARAMS, params)


def build(params, checkpoint):
    import cadquery as cq
    p = clamp_params(PARAMS, params)
    w, d, t = p["width"], p["depth"], p["thickness"]
    hole_d, margin = p["hole_d"], p["margin"]

    checkpoint("plate")
    plate = cq.Workplane("XY").box(w, d, t)

    checkpoint("fillet")
    fr = min(3.0, w / 2 - 1, d / 2 - 1)
    if fr > 0:
        plate = plate.edges("|Z").fillet(fr)

    checkpoint("holes")
    ox, oy = w / 2 - margin, d / 2 - margin
    if ox > hole_d and oy > hole_d:
        plate = (
            plate.faces(">Z").workplane()
            .pushPoints([(ox, oy), (-ox, oy), (ox, -oy), (-ox, -oy)])
            .hole(hole_d)
        )
    return plate
