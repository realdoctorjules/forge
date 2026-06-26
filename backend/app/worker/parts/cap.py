"""Round cap / lid / cover: a shelled cylinder, open on one end."""
from ._util import clamp_params, defaults as _defaults

PART_NAME = "cap"
PARAMS = {
    "diameter": {"value": 45.0, "min": 20.0, "max": 120.0, "step": 1.0, "unit": "mm", "label": "Diameter"},
    "height":   {"value": 22.0, "min": 8.0,  "max": 60.0,  "step": 1.0, "unit": "mm", "label": "Height"},
    "wall":     {"value": 2.0,  "min": 1.2,  "max": 4.0,   "step": 0.1, "unit": "mm", "label": "Wall thickness"},
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
    dia, h, wall = p["diameter"], p["height"], p["wall"]

    from ._util import safe_shell
    checkpoint("cylinder")
    body = cq.Workplane("XY").cylinder(h, dia / 2.0)

    checkpoint("shell_open_top")
    body = safe_shell(body, ">Z", wall)
    return body
