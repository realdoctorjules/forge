"""Real print estimates via PrusaSlicer CLI (when installed).

Slices an STL with a generated minimal profile and parses the g-code summary
for filament (g/cm3), cost, and estimated print time. Used on COMMIT (save/
generate/invent), not on live preview (slicing takes a few seconds). Falls back
to None on any problem so the caller keeps the heuristic estimate.
"""
from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import library

_CANDIDATES = [
    "/Applications/Original Prusa Drivers/PrusaSlicer.app/Contents/MacOS/PrusaSlicer",
    "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer",
]


def find_slicer() -> str | None:
    for c in _CANDIDATES:
        if Path(c).exists():
            return c
    return shutil.which("prusa-slicer") or shutil.which("PrusaSlicer")


def available() -> bool:
    return find_slicer() is not None


def _time_to_hours(s: str) -> float:
    h = m = sec = 0
    for val, unit in re.findall(r"(\d+)\s*([hms])", s):
        if unit == "h":
            h = int(val)
        elif unit == "m":
            m = int(val)
        elif unit == "s":
            sec = int(val)
    return round(h + m / 60 + sec / 3600, 2)


def slice_estimate(stl_path, material_key: str, *, layer_h: float = 0.2,
                   infill: int = 20, perimeters: int = 3, timeout: float = 30.0) -> dict | None:
    exe = find_slicer()
    stl_path = Path(stl_path)
    if not exe or not stl_path.exists():
        return None
    mat = library.MATERIALS.get(material_key, library.MATERIALS["PLA"])
    try:
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "cfg.ini"
            out = Path(td) / "out.gcode"
            cfg.write_text(
                f"layer_height = {layer_h}\nfirst_layer_height = {layer_h}\n"
                "nozzle_diameter = 0.4\nfilament_diameter = 1.75\n"
                f"filament_density = {mat['density']}\nfilament_cost = {mat['price_kg']}\n"
                f"perimeters = {perimeters}\ntop_solid_layers = 4\nbottom_solid_layers = 3\n"
                f"fill_density = {infill}%\nfill_pattern = grid\n"
                "temperature = 210\nfirst_layer_temperature = 215\n"
                "bed_temperature = 60\nfirst_layer_bed_temperature = 60\n")
            subprocess.run([exe, "--export-gcode", "--load", str(cfg),
                            "--output", str(out), str(stl_path)],
                           capture_output=True, timeout=timeout)
            if not out.exists():
                return None
            txt = out.read_text(errors="replace")
    except Exception:  # noqa: BLE001
        return None

    def grab(pat):
        m = re.search(pat, txt)
        return m.group(1).strip() if m else None

    grams = grab(r"total filament used \[g\]\s*=\s*([\d.]+)") or grab(r"filament used \[g\]\s*=\s*([\d.]+)")
    cm3 = grab(r"filament used \[cm3\]\s*=\s*([\d.]+)")
    cost = grab(r"total filament cost\s*=\s*([\d.]+)") or grab(r"filament cost\s*=\s*([\d.]+)")
    tstr = grab(r"estimated printing time \(normal mode\)\s*=\s*(.+)")
    if grams is None or tstr is None:
        return None
    return {
        "source": f"PrusaSlicer @ {layer_h} mm layers, {infill}% infill, {perimeters} perimeters",
        "filament_g": round(float(grams), 1),
        "filament_cm3": round(float(cm3), 2) if cm3 else None,
        "cost_usd": round(float(cost), 2) if cost else None,
        "print_time_h": _time_to_hours(tstr),
        "print_time_str": tstr,
    }
