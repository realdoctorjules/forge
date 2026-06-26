"""Wall hook — a back plate with a perpendicular arm."""
from ._util import clamp_params, defaults as _defaults

PART_NAME = "wall_hook"
PARAMS = {
    "width":       {"value": 20.0, "min": 10.0, "max": 50.0,  "step": 1.0, "unit": "mm", "label": "Width"},
    "back_height": {"value": 45.0, "min": 20.0, "max": 100.0, "step": 1.0, "unit": "mm", "label": "Back height"},
    "reach":       {"value": 28.0, "min": 10.0, "max": 70.0,  "step": 1.0, "unit": "mm", "label": "Hook reach"},
    "thickness":   {"value": 5.0,  "min": 2.5,  "max": 10.0,  "step": 0.5, "unit": "mm", "label": "Thickness"},
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
    w, bh, reach, t = p["width"], p["back_height"], p["reach"], p["thickness"]

    checkpoint("back_plate")
    back = cq.Workplane("XY").box(t, w, bh).translate((0, 0, bh / 2.0))

    checkpoint("arm")
    arm = cq.Workplane("XY").box(reach, w, t).translate((reach / 2.0 + t / 2.0, 0, t / 2.0))

    checkpoint("upturn")
    tip = cq.Workplane("XY").box(t, w, t * 2).translate((reach + t / 2.0, 0, t))

    checkpoint("union")
    return back.union(arm).union(tip)
