"""Dimensioned drawing sheet (printable HTML).

A titled engineering-style sheet: a to-scale orthographic envelope for each of
the three views (Front / Top / Right) with witness lines + measured overall
dimensions, the exact isometric line-art for shape reference, and a dimensions /
parameters table. Overall dimensions are exact (from the model bounding box);
internal witness-line dimensioning of every feature is a later step.
"""
from __future__ import annotations
import datetime
import html

from . import storage


def _ticked_dim_h(x0: float, y0: float, w: float, label: str) -> str:
    """Horizontal dimension line above a box edge, with end witness ticks."""
    y = y0 - 16
    return (
        f'<line x1="{x0}" y1="{y}" x2="{x0 + w}" y2="{y}" stroke="#555" stroke-width="1"/>'
        f'<line x1="{x0}" y1="{y - 4}" x2="{x0}" y2="{y0}" stroke="#999" stroke-width="0.7"/>'
        f'<line x1="{x0 + w}" y1="{y - 4}" x2="{x0 + w}" y2="{y0}" stroke="#999" stroke-width="0.7"/>'
        f'<text x="{x0 + w / 2}" y="{y - 4}" font-size="11" fill="#222" text-anchor="middle">{label}</text>'
    )


def _ticked_dim_v(x0: float, y0: float, h: float, label: str) -> str:
    """Vertical dimension line left of a box edge, with end witness ticks."""
    x = x0 - 16
    return (
        f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0 + h}" stroke="#555" stroke-width="1"/>'
        f'<line x1="{x - 4}" y1="{y0}" x2="{x0}" y2="{y0}" stroke="#999" stroke-width="0.7"/>'
        f'<line x1="{x - 4}" y1="{y0 + h}" x2="{x0}" y2="{y0 + h}" stroke="#999" stroke-width="0.7"/>'
        f'<text x="{x - 6}" y="{y0 + h / 2}" font-size="11" fill="#222" text-anchor="middle" '
        f'transform="rotate(-90 {x - 6} {y0 + h / 2})">{label}</text>'
    )


def _view(x0: float, y0: float, w_mm: float, h_mm: float, scale: float,
          title: str) -> str:
    w, h = w_mm * scale, h_mm * scale
    return (
        f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#f4f4f6" stroke="#222" stroke-width="1.5"/>'
        + _ticked_dim_h(x0, y0, w, f"{w_mm:g} mm")
        + _ticked_dim_v(x0, y0, h, f"{h_mm:g} mm")
        + f'<text x="{x0 + w / 2}" y="{y0 + h + 16}" font-size="11" fill="#555" text-anchor="middle">{title}</text>'
    )


def _envelope_svg(bb: dict) -> str:
    x, y, z = bb["x"], bb["y"], bb["z"]
    scale = 150.0 / max(x, y, z, 1)
    # three views laid out left→right with generous gaps for the dim lines
    pad_left, pad_top, gap = 60, 40, 70
    cx = pad_left
    parts = []
    for (wmm, hmm, title) in [(x, z, "FRONT (X × Z)"), (x, y, "TOP (X × Y)"), (y, z, "RIGHT (Y × Z)")]:
        parts.append(_view(cx, pad_top, wmm, hmm, scale, title))
        cx += wmm * scale + gap
    width = cx + 20
    height = pad_top + max(z, y, z) * scale + 60
    return (f'<svg width="{width:.0f}" height="{height:.0f}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>')


def build_sheet(version: dict) -> str:
    m = version.get("metrics") or {}
    g = m.get("geometry") or {}
    a = m.get("analysis") or {}
    bb = g.get("bbox_mm") or {"x": 0, "y": 0, "z": 0}
    name = m.get("name") or m.get("archetype_label") or "Device"
    material = a.get("material") or m.get("material") or "PLA"
    date = datetime.date.today().isoformat()

    params = version.get("params") or {}
    param_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{v}</td></tr>" for k, v in params.items()
    ) or "<tr><td colspan='2'>AI-generated geometry (no editable parameters)</td></tr>"

    iso_path = storage.version_dir(version["project_id"], version["id"]) / "view_iso.svg"
    iso_svg = iso_path.read_text() if iso_path.exists() else ""

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(name)} — drawing</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1a1a1a}}
.title{{display:flex;justify-content:space-between;border:2px solid #222;padding:10px 14px;border-radius:4px}}
.title h1{{font-size:18px;margin:0}}
.title .meta{{font-size:12px;color:#444;text-align:right;line-height:1.6}}
h2{{font-size:14px;margin:22px 0 6px;color:#333}}
.fig{{border:1px solid #ccc;border-radius:4px;padding:8px;text-align:center;background:#fff}}
table{{border-collapse:collapse;font-size:13px;margin-top:6px}} td,th{{border:1px solid #ccc;padding:5px 10px;text-align:left}}
.note{{font-size:11px;color:#777;margin-top:10px}}
.cols{{display:flex;gap:18px;flex-wrap:wrap}} .cols>div{{flex:1;min-width:280px}}
</style></head><body>
<div class="title">
  <div><h1>{html.escape(name)}</h1><div style="font-size:12px;color:#555">Forge drawing — DRAFT</div></div>
  <div class="meta">Version v{version['id']}<br>Material: {html.escape(material)}<br>Date: {date}<br>Units: millimetres</div>
</div>

<h2>Orthographic views — overall dimensions (to scale)</h2>
<div class="fig">{_envelope_svg(bb)}</div>

<div class="cols">
  <div>
    <h2>Isometric (exact shape)</h2>
    <div class="fig">{iso_svg or 'no isometric view'}</div>
  </div>
  <div>
    <h2>Dimensions &amp; parameters</h2>
    <table>
      <tr><th>Property</th><th>Value</th></tr>
      <tr><td>Overall L × W × H</td><td>{bb['x']:g} × {bb['y']:g} × {bb['z']:g} mm</td></tr>
      <tr><td>Volume</td><td>{a.get('volume_cm3', '—')} cm³</td></tr>
      <tr><td>Est. weight ({html.escape(material)})</td><td>{a.get('mass_g', '—')} g</td></tr>
      {param_rows}
    </table>
  </div>
</div>

<p class="note">Overall envelope dimensions are exact (from the model bounding box) and drawn to scale.
The isometric is the exact projected geometry. Per-feature witness-line dimensioning and full
37 CFR 1.84 compliance are not yet automated. Forge draft — not for manufacturing release.</p>
</body></html>"""
