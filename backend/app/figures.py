"""Patent draft figures.

Turns the worker's exact line-art (OCCT hidden-line-removed SVG projections) into
USPTO-draft-style figures: numbered FIGs, black line-art on white, NO dimension
lines, and reference numerals connected to the device by leader lines.

The leader anchors are derived from the actual drawn silhouette (parsed from the
SVG path coordinates), so a numeral points at the device rather than floating in
a side table. Placement is a DRAFT: an attorney sets the exact feature each
numeral targets and finalizes line weights/shading per 37 CFR 1.84.
"""
from __future__ import annotations
import html
import math
import re

from . import patent, storage

_NUM_RE = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")
_SCALE_RE = re.compile(r"scale\(\s*([-\d.eE]+)\s*,?\s*([-\d.eE]+)?\s*\)")
_TRANS_RE = re.compile(r"translate\(\s*([-\d.eE]+)\s*,?\s*([-\d.eE]+)?\s*\)")
_PATHS_RE = re.compile(r'<path[^>]*\bd="([^"]*)"', re.DOTALL)
_GBODY_RE = re.compile(r"<g\b[^>]*>.*</g>", re.DOTALL)

CANVAS_W, CANVAS_H = 440.0, 340.0


def _transform(svg: str) -> tuple[float, float, float, float]:
    """(sx, sy, tx, ty) from the OCCT wrapper <g transform="scale(...) translate(...)">."""
    sx = sy = 1.0
    tx = ty = 0.0
    ms = _SCALE_RE.search(svg)
    if ms:
        sx = float(ms.group(1))
        sy = float(ms.group(2)) if ms.group(2) else sx
    mt = _TRANS_RE.search(svg)
    if mt:
        tx = float(mt.group(1))
        ty = float(mt.group(2)) if mt.group(2) else 0.0
    return sx, sy, tx, ty


def _silhouette_bbox(svg: str) -> tuple[float, float, float, float] | None:
    """Bounding box of the drawn geometry, in CANVAS pixels."""
    sx, sy, tx, ty = _transform(svg)
    xs: list[float] = []
    ys: list[float] = []
    for d in _PATHS_RE.findall(svg):
        nums = [float(n) for n in _NUM_RE.findall(d)]
        for i in range(0, len(nums) - 1, 2):
            x, y = nums[i], nums[i + 1]
            xs.append(sx * (x + tx))   # SVG applies scale() to translate()'d coords
            ys.append(sy * (y + ty))
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _occt_lineart(svg: str) -> str:
    """The inner <g>…</g> line-art, ready to drop into another <svg>."""
    m = _GBODY_RE.search(svg)
    return m.group(0) if m else ""


def _ray_to_box(cx: float, cy: float, ang: float,
                x0: float, y0: float, x1: float, y1: float) -> tuple[float, float]:
    """Point where a ray from the centre at angle `ang` meets the bbox rectangle."""
    dx, dy = math.cos(ang), math.sin(ang)
    best = (x1, cy)
    t_best = float("inf")
    for t_edge, on in (
        ((x1 - cx) / dx if dx else None, "x"),
        ((x0 - cx) / dx if dx else None, "x"),
        ((y1 - cy) / dy if dy else None, "y"),
        ((y0 - cy) / dy if dy else None, "y"),
    ):
        if t_edge is None or t_edge <= 0:
            continue
        px, py = cx + dx * t_edge, cy + dy * t_edge
        if x0 - 0.5 <= px <= x1 + 0.5 and y0 - 0.5 <= py <= y1 + 0.5 and t_edge < t_best:
            t_best, best = t_edge, (px, py)
    return best


def numbered_figure_svg(svg: str, feats: list[dict]) -> str:
    """OCCT line-art + reference-numeral leader lines, as one <svg> (viewBox padded
    so numerals sit outside the drawing)."""
    art = _occt_lineart(svg)
    bb = _silhouette_bbox(svg)
    if not bb:
        return f'<svg width="{CANVAS_W:.0f}" height="{CANVAS_H:.0f}">{art}</svg>'
    x0, y0, x1, y1 = bb
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    overlay = []
    n = max(1, len(feats))
    for i, f in enumerate(feats):
        if i == 0:
            # the body / device as a whole -> leader to the centroid
            ax, ay = cx, cy
            ang = math.radians(150)
        else:
            ang = math.radians(-90 + (360.0 / n) * i)
            ax, ay = _ray_to_box(cx, cy, ang, x0, y0, x1, y1)
        lx, ly = ax + 30 * math.cos(ang), ay + 30 * math.sin(ang)
        overlay.append(
            f'<line x1="{lx:.1f}" y1="{ly:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" '
            f'stroke="#000" stroke-width="0.6"/>'
            f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="1.3" fill="#000"/>'
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-family="Arial,Helvetica,sans-serif" '
            f'font-size="13" fill="#000" text-anchor="middle" dominant-baseline="middle" '
            f'dy="{-7 if math.sin(ang) < 0 else 11:.0f}">{f["num"]}</text>'
        )
    pad = 44
    vb = f"{-pad} {-pad} {CANVAS_W + 2 * pad:.0f} {CANVAS_H + 2 * pad:.0f}"
    return (f'<svg viewBox="{vb}" width="{CANVAS_W + 2 * pad:.0f}" '
            f'height="{CANVAS_H + 2 * pad:.0f}" xmlns="http://www.w3.org/2000/svg">'
            f'{art}{"".join(overlay)}</svg>')


_VIEW_FIG = {"iso": "perspective view", "front": "front elevation",
             "top": "top plan view", "right": "right side elevation"}


def build_sheet(version: dict) -> str:
    """Full patent figure sheet (HTML): numbered FIGs, numerals on FIG. 1, no dims."""
    ctx = patent._context(version)
    feats = ctx["features"]
    vd = storage.version_dir(version["project_id"], version["id"])

    order = [v for v in ("iso", "front", "top", "right") if (vd / f"view_{v}.svg").exists()]
    if not order:
        body = ('<p style="color:#b00">No line-art views were generated for this '
                'version, so figures cannot be drawn. Re-build the device and try again.</p>')
        figs_html = body
    else:
        blocks = []
        for idx, view in enumerate(order, start=1):
            raw = (vd / f"view_{view}.svg").read_text()
            svg = numbered_figure_svg(raw, feats) if view == "iso" else \
                f'<svg width="{CANVAS_W:.0f}" height="{CANVAS_H:.0f}" ' \
                f'viewBox="0 0 {CANVAS_W:.0f} {CANVAS_H:.0f}" ' \
                f'xmlns="http://www.w3.org/2000/svg">{_occt_lineart(raw)}</svg>'
            note = " (reference numerals shown)" if view == "iso" else ""
            blocks.append(
                f'<figure class="fig"><div class="art">{svg}</div>'
                f'<figcaption>FIG. {idx} &mdash; {_VIEW_FIG.get(view, view)}{note}</figcaption>'
                f'</figure>')
        figs_html = "".join(blocks)

    ref_rows = "".join(
        f'<tr><td class="num">{f["num"]}</td><td>{html.escape(f["name"])}</td></tr>'
        for f in feats)
    title = html.escape(ctx["name"])
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{title} — patent figures (draft)</title>
<style>
  body{{font-family:Arial,Helvetica,sans-serif;color:#000;background:#fff;
       max-width:840px;margin:24px auto;padding:0 24px}}
  h1{{font-size:18px;margin:0 0 2px}} .sub{{color:#555;font-size:12px;margin-bottom:18px}}
  .fig{{margin:0 0 26px;text-align:center;page-break-inside:avoid}}
  .art{{border:1px solid #e3e3e3;background:#fff;display:inline-block;padding:6px;max-width:100%}}
  .art svg{{max-width:100%;height:auto}}
  figcaption{{font-size:13px;font-weight:bold;letter-spacing:.3px;margin-top:6px}}
  table{{border-collapse:collapse;font-size:13px;margin-top:6px}}
  td{{border:1px solid #ccc;padding:4px 10px}} td.num{{text-align:center;font-weight:bold;width:48px}}
  h2{{font-size:14px;margin-top:24px;border-bottom:1px solid #ddd;padding-bottom:3px}}
  .note{{font-size:11px;color:#666;margin-top:18px;line-height:1.5}}
  @media print{{ .art{{border:none}} body{{margin:0}} }}
</style></head><body>
<h1>{title} — Drawings</h1>
<div class="sub">Patent-style figure sheet (DRAFT). Black line-art, no dimensions —
exact projections from the model. Sheet 1 of 1.</div>
{figs_html}
<h2>Reference Numerals</h2>
<table>{ref_rows}</table>
<div class="note">
  Leader lines connect each numeral to the device on FIG. 1; their anchor points
  are draft placements derived from the drawn silhouette, not a substitute for an
  attorney/draftsperson assigning each numeral to its exact feature. Formal filing
  drawings must meet 37 CFR 1.84 (line weight, surface shading, sheet/margin sizes,
  view numbering). Generated by Forge as a drafting aid — not a filing, not legal advice.
</div>
</body></html>"""
