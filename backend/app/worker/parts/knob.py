"""Control knob / dial: a chamfered cylinder with a shaft bore."""
from ._util import clamp_params, defaults as _defaults

PART_NAME = "knob"
PARAMS = {
    "diameter": {"value": 32.0, "min": 15.0, "max": 70.0, "step": 1.0, "unit": "mm", "label": "Diameter"},
    "height":   {"value": 18.0, "min": 8.0,  "max": 45.0, "step": 1.0, "unit": "mm", "label": "Height"},
    "shaft_d":  {"value": 6.0,  "min": 3.0,  "max": 14.0, "step": 0.5, "unit": "mm", "label": "Shaft bore"},
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
    dia, h, shaft = p["diameter"], p["height"], p["shaft_d"]

    checkpoint("cylinder")
    body = cq.Workplane("XY").cylinder(h, dia / 2.0)

    checkpoint("chamfer")
    ch = min(2.0, dia * 0.08, h * 0.2)
    if ch > 0.2:
        body = body.edges(">Z").chamfer(ch)

    checkpoint("shaft_bore")
    if shaft < dia - 4:
        body = body.faces("<Z").workplane().hole(shaft, h * 0.6)
    return body
