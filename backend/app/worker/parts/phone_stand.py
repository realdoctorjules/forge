"""Angled stand / wedge — a phone or tablet rests against the slope."""
from ._util import clamp_params, defaults as _defaults

PART_NAME = "phone_stand"
PARAMS = {
    "width":  {"value": 80.0, "min": 50.0, "max": 150.0, "step": 1.0, "unit": "mm", "label": "Width"},
    "depth":  {"value": 70.0, "min": 40.0, "max": 140.0, "step": 1.0, "unit": "mm", "label": "Base depth"},
    "height": {"value": 95.0, "min": 50.0, "max": 170.0, "step": 1.0, "unit": "mm", "label": "Back height"},
}
DEFAULT_MATERIAL = "PETG"
STANDARD_PARTS: list = []


def defaults():
    return _defaults(PARAMS)


def clamp(params):
    return clamp_params(PARAMS, params)


def build(params, checkpoint):
    import cadquery as cq
    p = clamp_params(PARAMS, params)
    w, d, h = p["width"], p["depth"], p["height"]
    checkpoint("profile")
    # side profile (x = depth, y = height); the hypotenuse is the rest surface
    body = cq.Workplane("XY").polyline([(0, 0), (d, 0), (0, h)]).close().extrude(w)
    checkpoint("fillet")
    fr = min(3.0, w / 4)
    if fr > 0:
        body = body.edges("|X").fillet(fr)
    return body
