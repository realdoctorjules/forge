"""Electronics component library + clearance-budget fit check.

Per the hardened plan: NOT a binary "it fits" — a clearance-budget estimate
(best-fit orientation) against a minimum margin (default 1.5 mm), with
component-specific warnings (battery swell, antenna keep-out). Dimensions are
nominal bounding boxes in mm (L x W x H).
"""
from __future__ import annotations

COMPONENTS: dict = {
    "esp32_devkit":   {"name": "ESP32 DevKit", "l": 51, "w": 28, "h": 13,
                       "note": "Leave ~10 mm clear over the antenna end (no metal/ground plane)."},
    "esp32_c3_mini":  {"name": "ESP32-C3 Mini", "l": 35, "w": 25, "h": 8,
                       "note": "Keep the PCB antenna corner clear of metal."},
    "arduino_nano":   {"name": "Arduino Nano", "l": 45, "w": 18, "h": 7, "note": ""},
    "rpi_zero_2w":    {"name": "Raspberry Pi Zero 2 W", "l": 65, "w": 30, "h": 5,
                       "note": "Add height for the GPIO header (~9 mm) if populated."},
    "rpi_4b":         {"name": "Raspberry Pi 4B", "l": 85, "w": 56, "h": 17,
                       "note": "Runs hot — leave airflow/heatsink clearance."},
    "battery_18650":  {"name": "18650 Li-ion cell", "l": 65, "w": 18, "h": 18,
                       "note": "Li-ion can swell — add ≥1 mm extra and never trap it tightly."},
    "lipo_500mah":    {"name": "LiPo 500 mAh", "l": 35, "w": 25, "h": 6,
                       "note": "LiPo swells with age/heat — leave swell room; protect from puncture."},
    "coin_cr2032":    {"name": "Coin cell CR2032", "l": 20, "w": 20, "h": 3, "note": ""},
    "oled_128x64":    {"name": "OLED 0.96\" (SSD1306)", "l": 27, "w": 27, "h": 4,
                       "note": "Display window must align with a cutout."},
    "usb_c_breakout": {"name": "USB-C breakout", "l": 15, "w": 13, "h": 6,
                       "note": "Port must reach the wall — align with a cutout."},
    "toggle_switch":  {"name": "Toggle switch", "l": 13, "w": 13, "h": 25,
                       "note": "Height includes the shaft above the panel."},
}


def list_components() -> list[dict]:
    return [{"key": k, **v} for k, v in COMPONENTS.items()]


def fit_check(interior: dict, component_key: str, clearance_min: float = 1.5) -> dict:
    c = COMPONENTS.get(component_key)
    if not c:
        return {"error": "unknown component"}
    # best-fit orientation: sort both envelopes descending and compare axis-wise
    ci = sorted([interior["l"], interior["w"], interior["h"]], reverse=True)
    cc = sorted([float(c["l"]), float(c["w"]), float(c["h"])], reverse=True)
    margins = [round(ci[i] - cc[i], 1) for i in range(3)]
    min_margin = min(margins)
    fits = min_margin >= 0
    warnings = []
    if not fits:
        warnings.append(f"Does NOT fit — too big by {abs(min_margin)} mm on the tightest axis.")
    elif min_margin < clearance_min:
        warnings.append(f"Very tight — only {min_margin} mm spare (recommend ≥ {clearance_min} mm).")
    if c.get("note"):
        warnings.append(c["note"])
    return {
        "component": c["name"], "component_lwh": [c["l"], c["w"], c["h"]],
        "interior_lwh": [round(interior["l"], 1), round(interior["w"], 1), round(interior["h"], 1)],
        "fits": fits, "tight": fits and min_margin < clearance_min,
        "min_margin_mm": min_margin, "margins_sorted_mm": margins,
        "clearance_min_mm": clearance_min, "warnings": warnings,
    }
