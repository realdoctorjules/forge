"""Device library: parametric archetypes, materials, prompt matching, and the
cost / weight / BOM analysis.

This is the constrained device family from the hardened plan. Until an Anthropic
API key is wired (P-B, gated behind SPIKE-1), a prompt is matched to the closest
archetype here by keyword. With a key, the LLM will instead author parametric
code directly — but everything downstream (analysis, exports, patent) is the same.
"""
from __future__ import annotations
import math
import re

from .worker.parts import (hello_enclosure, tray, cap, bracket, knob,
                           phone_stand, cable_clip, wall_hook)

ARCHETYPES: dict = {
    "enclosure": {
        "label": "Enclosure / case",
        "module": "hello_enclosure",
        "mod": hello_enclosure,
        "keywords": ["enclosure", "case", "box", "housing", "project box", "container", "shell"],
        "examples": ["a 60x40x25mm project box", "a small electronics enclosure"],
    },
    "tray": {
        "label": "Tray / organizer",
        "module": "tray",
        "mod": tray,
        "keywords": ["tray", "organizer", "compartment", "pill", "divider", "sorter",
                     "slots", "weekly", "bins", "caddy"],
        "examples": ["a 7-compartment weekly pill organizer", "a parts tray with 3x2 bins"],
    },
    "cap": {
        "label": "Cap / lid",
        "module": "cap",
        "mod": cap,
        "keywords": ["cap", "lid", "cover", "plug", "top", "bottle"],
        "examples": ["a 45mm jar lid", "a protective cap"],
    },
    "bracket": {
        "label": "Bracket / mounting plate",
        "module": "bracket",
        "mod": bracket,
        "keywords": ["bracket", "mount", "plate", "holder", "support", "clamp", "flange"],
        "examples": ["a mounting plate with 4 screw holes", "an L-bracket"],
    },
    "knob": {
        "label": "Knob / dial",
        "module": "knob",
        "mod": knob,
        "keywords": ["knob", "dial", "handle", "grip", "wheel", "control"],
        "examples": ["a control knob for a 6mm shaft", "a dial"],
    },
    "phone_stand": {
        "label": "Stand / holder",
        "module": "phone_stand",
        "mod": phone_stand,
        "keywords": ["stand", "holder", "wedge", "phone", "tablet", "prop", "easel", "dock"],
        "examples": ["a phone stand", "a tablet holder"],
    },
    "cable_clip": {
        "label": "Cable clip",
        "module": "cable_clip",
        "mod": cable_clip,
        "keywords": ["clip", "cable", "cord", "wire", "tube", "hose", "snap"],
        "examples": ["a clip for an 8mm cable", "a cord organizer clip"],
    },
    "wall_hook": {
        "label": "Wall hook",
        "module": "wall_hook",
        "mod": wall_hook,
        "keywords": ["hook", "hanger", "peg", "rack", "hang"],
        "examples": ["a wall hook", "a hook to hang a bag"],
    },
}

# density g/cm^3, price USD/kg (rough, configurable later)
MATERIALS: dict = {
    "PLA":   {"name": "PLA",        "density": 1.24, "price_kg": 25.0},
    "PETG":  {"name": "PETG",       "density": 1.27, "price_kg": 28.0},
    "ABS":   {"name": "ABS",        "density": 1.04, "price_kg": 26.0},
    "TPU":   {"name": "TPU (flex)", "density": 1.21, "price_kg": 42.0},
    "Resin": {"name": "Resin (SLA)", "density": 1.15, "price_kg": 55.0},
    "Nylon": {"name": "Nylon (PA12)", "density": 1.01, "price_kg": 70.0},
}


def list_archetypes() -> list[dict]:
    out = []
    for key, a in ARCHETYPES.items():
        mod = a["mod"]
        out.append({
            "key": key,
            "label": a["label"],
            "examples": a["examples"],
            "params": mod.PARAMS,
            "defaults": defaults(key),
            "default_material": getattr(mod, "DEFAULT_MATERIAL", "PLA"),
        })
    return out


def list_materials() -> list[dict]:
    return [{"key": k, **v} for k, v in MATERIALS.items()]


def module_name(archetype: str) -> str:
    return ARCHETYPES[archetype]["module"]


def standard_parts(archetype: str) -> list:
    return list(getattr(ARCHETYPES[archetype]["mod"], "STANDARD_PARTS", []))


def defaults(archetype: str) -> dict:
    mod = ARCHETYPES[archetype]["mod"]
    if hasattr(mod, "defaults"):
        return mod.defaults()
    return {k: v["value"] for k, v in mod.PARAMS.items()}


def clamp(archetype: str, params: dict) -> dict:
    mod = ARCHETYPES[archetype]["mod"]
    if hasattr(mod, "clamp"):
        return mod.clamp(params)
    from .worker.parts._util import clamp_params
    return clamp_params(mod.PARAMS, params)


def match(prompt: str) -> dict:
    """Map a free-text prompt to the closest archetype + sensible param overrides."""
    text = (prompt or "").lower()
    best, best_score = "enclosure", 0
    for key, a in ARCHETYPES.items():
        score = sum(1 for kw in a["keywords"] if kw in text)
        if score > best_score:
            best, best_score = key, score

    params = defaults(best)
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]

    if best == "tray":
        count = None
        m = re.search(r"(\d+)\s*(?:compartment|slot|bin|cell|section|day)", text)
        if m:
            count = int(m.group(1))
        elif "weekly" in text or "week" in text:
            count = 7
        if count:
            cols = min(count, 7)
            rows = max(1, math.ceil(count / cols))
            params["cols"], params["rows"] = cols, rows
        gxg = re.search(r"(\d+)\s*[x×]\s*(\d+)", text)
        if gxg:
            params["cols"], params["rows"] = int(gxg.group(1)), int(gxg.group(2))

    # crude dimension capture: "60x40x25" -> width/depth/height when present
    dims = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)", text)
    if dims and {"width", "depth", "height"} <= set(params):
        params["width"], params["depth"], params["height"] = (
            float(dims.group(1)), float(dims.group(2)), float(dims.group(3)))

    params = clamp(best, params)
    name = _name_from_prompt(prompt) or ARCHETYPES[best]["label"]
    fit = "good" if best_score >= 1 else "out_of_scope"
    fit_note = ("" if best_score >= 1 else
                "No close match in the device library — showing the nearest simple part "
                "as a stand-in, not the device you described.")
    alts = [] if best_score >= 1 else [
        {"label": ARCHETYPES[k]["label"], "prompt": ARCHETYPES[k]["examples"][0]}
        for k in ("enclosure", "bracket", "tray")]
    return {"archetype": best, "params": params, "name": name, "match_score": best_score,
            "fit": fit, "fit_note": fit_note, "alternatives": alts}


def _name_from_prompt(prompt: str) -> str:
    p = (prompt or "").strip()
    if not p:
        return ""
    words = re.sub(r"\s+", " ", p).split(" ")[:7]
    return " ".join(words)[:60]


def analyze(volume_mm3: float, material_key: str, std_parts: list) -> dict:
    mat = MATERIALS.get(material_key, MATERIALS["PLA"])
    vol_cm3 = volume_mm3 / 1000.0
    mass_g = vol_cm3 * mat["density"]
    filament_cost = mass_g / 1000.0 * mat["price_kg"]
    parts_cost = sum(sp["qty"] * sp.get("unit_cost", 0.0) for sp in std_parts)
    cost = filament_cost + parts_cost
    rate_cm3_h = 11.0           # rough FDM deposition rate
    time_h = vol_cm3 / rate_cm3_h + 0.15

    components = [{
        "name": "printed body", "type": "3D-printed", "qty": 1,
        "material": mat["name"], "mass_g": round(mass_g, 1),
        "cost_usd": round(filament_cost, 2),
    }]
    for sp in std_parts:
        components.append({
            "name": sp["name"], "type": "hardware", "qty": sp["qty"],
            "material": "steel", "mass_g": None,
            "cost_usd": round(sp["qty"] * sp.get("unit_cost", 0.0), 2),
        })
    component_count = sum(c["qty"] for c in components)

    def rng(v, frac):
        return [round(v * (1 - frac), 2), round(v * (1 + frac), 2)]

    return {
        "material": mat["name"],
        "material_key": material_key,
        "density_g_cm3": mat["density"],
        "volume_cm3": round(vol_cm3, 2),
        "mass_g": round(mass_g, 1),
        "mass_g_range": rng(mass_g, 0.15),
        "filament_cost_usd": round(filament_cost, 2),
        "parts_cost_usd": round(parts_cost, 2),
        "cost_usd": round(cost, 2),
        "cost_usd_range": rng(cost, 0.20),
        "print_time_h": round(time_h, 2),
        "print_time_h_range": rng(time_h, 0.40),
        "components": components,
        "component_count": component_count,
        "confidence": "rough pre-slicer estimate — ranges shown; do not make irreversible decisions on these",
    }


def dfm_check(archetype: str, params: dict, geom: dict) -> list[dict]:
    """Quick design-for-3D-printing sanity checks. Heuristic, not a slicer."""
    out: list[dict] = []
    wall = params.get("wall", params.get("thickness"))
    if wall is not None and wall < 0.8:
        out.append({"level": "warn",
                    "msg": f"Wall/thickness {wall} mm is below ~0.8 mm (2× a 0.4 mm nozzle) — may not print solid."})
    bb = geom.get("bbox_mm") or {}
    dims = [v for v in (bb.get("x"), bb.get("y"), bb.get("z")) if v]
    if dims and min(dims) < 3:
        out.append({"level": "warn",
                    "msg": f"Smallest dimension {min(dims)} mm is very thin — fragile and hard to print."})
    hole = params.get("hole_d", params.get("shaft_d"))
    if hole is not None and hole < 1.5:
        out.append({"level": "warn",
                    "msg": f"Hole {hole} mm is tiny — it may close up when printed."})
    z = bb.get("z")
    foot = min([v for v in (bb.get("x"), bb.get("y")) if v], default=None)
    if z and foot and z > foot * 3:
        out.append({"level": "info",
                    "msg": "Tall and narrow — add a brim or print on its side for stability."})
    if not out:
        out.append({"level": "ok", "msg": "No obvious print problems detected."})
    return out
