"""Attorney-review-ready provisional patent DRAFT generator.

Deterministic scaffold (works with no API key): reference numerals, a brief
description of drawings, a §112(a) support-coverage map, a filing checklist, the
legal gates (attorney-review banner, disclosure-clock note, patient-contact
STOP), and a simple figure. When an Anthropic key is set, Claude writes the
prose sections (title/background/summary/detailed description/claims/abstract);
the numerals, figures, coverage map, checklist, and gates stay deterministic.

NOT legal advice. NOT a filing. A draft for a licensed patent attorney.
"""
from __future__ import annotations
import html
import json

from . import ai, storage

# Structural features per archetype, in numeral order (10, 12, 14, ...)
FEATURES = {
    "enclosure": ["housing", "side wall", "interior cavity", "open top edge"],
    "tray": ["tray body", "compartment", "dividing wall", "perimeter wall"],
    "cap": ["cap body", "cylindrical side wall", "closed end", "open end"],
    "bracket": ["mounting plate", "fastener hole", "filleted edge"],
    "knob": ["knob body", "gripping surface", "shaft bore", "chamfered edge"],
    "imported": ["body"],
}


def _numerals(archetype: str) -> list[dict]:
    feats = FEATURES.get(archetype, FEATURES["imported"])
    return [{"num": 10 + 2 * i, "name": f} for i, f in enumerate(feats)]


def _context(version: dict) -> dict:
    m = version.get("metrics") or {}
    g = m.get("geometry") or {}
    a = m.get("analysis") or {}
    archetype = m.get("archetype", "imported")
    return {
        "name": m.get("name") or m.get("archetype_label") or "Device",
        "device_type": m.get("archetype_label", "device"),
        "archetype": archetype,
        "material": a.get("material") or m.get("material") or "PLA",
        "dimensions_mm": g.get("bbox_mm"),
        "volume_cm3": a.get("volume_cm3") or g.get("volume_cm3"),
        "mass_g": a.get("mass_g"),
        "component_count": a.get("component_count"),
        "components": a.get("components"),
        "params": version.get("params") or {},
        "features": _numerals(archetype),
    }


def _deterministic_sections(ctx: dict) -> dict:
    name = ctx["name"]
    feats = ctx["features"]
    body = feats[0]["name"] if feats else "device"
    body_num = feats[0]["num"] if feats else 10
    dims = ctx.get("dimensions_mm") or {}
    dim_txt = (f"approximately {dims.get('x')} mm by {dims.get('y')} mm by "
               f"{dims.get('z')} mm" if dims else "the dimensions set out below")
    feat_clause = "; ".join(f"a {f['name']} ({f['num']})" for f in feats)

    return {
        "title": name.upper(),
        "field": f"The present disclosure relates to a {ctx['device_type'].lower()}, "
                 f"and more particularly to a {body} and associated features for the same.",
        "background": (
            "Devices of this general type are used in a variety of settings. Existing "
            "approaches can be improved upon with respect to manufacturability, part "
            "count, and ease of fabrication. There remains a need for a device that is "
            "straightforward to produce, including by additive manufacturing, while "
            "providing the structure described herein. [Attorney to expand with the "
            "specific problem addressed and the limitations of known approaches.]"),
        "summary": (
            f"Disclosed is a {body} ({body_num}) comprising " + feat_clause + ". "
            f"In one implementation the device measures {dim_txt} and is formed of "
            f"{ctx['material']}. The arrangement of features described herein enables the "
            "device to be produced as a small number of components suitable for additive "
            "manufacturing."),
        "detailed_description": (
            "Referring to FIG. 1, a " + body + " (" + str(body_num) + ") is shown. "
            + " ".join(f"The {f['name']} ({f['num']}) is configured as described herein."
                       for f in feats)
            + f" In the illustrated implementation the overall envelope is {dim_txt}, "
            f"and the device is formed of {ctx['material']}. Dimensions, wall thicknesses, "
            "and feature counts may be varied within the ranges that preserve the "
            "described function. [Attorney to expand with operation, alternatives, and "
            "enablement detail.]"),
        "claims": _deterministic_claims(ctx),
        "abstract": (
            f"A {body} ({body_num}) and related features, including " + feat_clause +
            f". The device, in one implementation measuring {dim_txt} and formed of "
            f"{ctx['material']}, is configured for production as a small number of "
            "additively-manufacturable components."),
        "source": "deterministic",
    }


def _deterministic_claims(ctx: dict) -> list[str]:
    feats = ctx["features"]
    body = feats[0]["name"] if feats else "device"
    indep = (f"1. A {body} comprising: " +
             "; ".join(f"a {f['name']}" for f in feats[1:]) +
             (";" if len(feats) > 1 else "") +
             f" wherein the {body} is configured for additive manufacturing.")
    claims = [indep]
    n = 2
    if ctx.get("material"):
        claims.append(f"{n}. The {body} of claim 1, wherein the {body} is formed of "
                      f"{ctx['material']}.")
        n += 1
    if ctx.get("dimensions_mm"):
        d = ctx["dimensions_mm"]
        claims.append(f"{n}. The {body} of claim 1, having an overall envelope of "
                      f"about {d.get('x')} mm by {d.get('y')} mm by {d.get('z')} mm.")
        n += 1
    return claims


def _coverage(ctx: dict, sections: dict) -> dict:
    rows = []
    for f in ctx["features"]:
        rows.append({"limitation": f["name"], "numeral": f["num"],
                     "supported": True,
                     "where": "Detailed Description + FIG. 1"})
    for k, v in (ctx.get("params") or {}).items():
        rows.append({"limitation": f"parameter: {k} = {v}", "numeral": None,
                     "supported": True, "where": "Summary / Detailed Description"})
    gaps = []
    # If AI wrote claims, flag that limitations should be re-verified by counsel.
    if sections.get("source") == "ai":
        gaps.append("AI-drafted claims: have counsel verify every limitation traces to "
                    "a described feature and figure numeral before filing.")
    return {"rows": rows, "gaps": gaps}


FILING_CHECKLIST = [
    "Confirm inventorship: every person who contributed to the conception of a claim "
    "is named (see the project's inventorship log).",
    "Have a licensed patent attorney or agent review and revise this draft — especially "
    "the claims and the §112(a) written-description/enablement support.",
    "Prepare formal drawings meeting 37 CFR 1.84 (the figure here is a schematic only).",
    "Complete a USPTO Provisional Application Cover Sheet (form SB/16) and verify "
    "micro/small-entity status for the fee.",
    "File via USPTO Patent Center and docket the 12-month deadline to file a "
    "non-provisional (and any foreign/PCT) application.",
    "Do NOT publicly disclose, offer for sale, or sell the device before filing without "
    "understanding the on-sale/public-use bar and the loss of most foreign rights.",
]


def build(version: dict, *, patient_contact: bool, want_ai: bool = True) -> dict:
    ctx = _context(version)

    sections = _deterministic_sections(ctx)
    ai_note = "Deterministic draft (no AI key set)."
    if want_ai and ai.enabled():
        try:
            ai_sections = ai.draft_patent_sections(ctx)
            for k in ("title", "field", "background", "summary",
                      "detailed_description", "abstract"):
                if ai_sections.get(k):
                    sections[k] = ai_sections[k]
            if isinstance(ai_sections.get("claims"), list) and ai_sections["claims"]:
                sections["claims"] = ai_sections["claims"]
            sections["source"] = "ai"
            ai_note = "Prose drafted by Claude (claude-opus-4-8); attorney review required."
        except Exception as e:  # noqa: BLE001
            ai_note = f"AI draft failed ({e}); used deterministic draft."

    coverage = _coverage(ctx, sections)
    gates = _gates(patient_contact)

    payload = {
        "name": ctx["name"], "device_type": ctx["device_type"],
        "numerals": ctx["features"], "sections": sections,
        "coverage": coverage, "checklist": FILING_CHECKLIST,
        "gates": gates, "ai_note": ai_note,
        "is_filing": False,
    }

    vd = storage.version_dir(version["project_id"], version["id"])
    iso = vd / "view_iso.svg"
    figure_svg = iso.read_text() if iso.exists() else None
    payload["has_real_figure"] = bool(figure_svg)
    (vd / "patent.json").write_text(json.dumps(payload, indent=2))
    (vd / "patent.html").write_text(_render_html(ctx, payload, figure_svg))
    (vd / "patent.md").write_text(_render_md(payload))
    payload["files"] = {
        "html": f"/api/versions/{version['id']}/patent.html",
        "md": f"/api/versions/{version['id']}/patent.md",
    }
    return payload


def _gates(patient_contact: bool) -> dict:
    g = {
        "attorney_banner": "ATTORNEY-REVIEW-READY DRAFT — NOT A FILING. This document "
        "is a starting point for a licensed patent attorney. It is not legal advice and "
        "has not been filed with any patent office.",
        "disclosure_clock": "Disclosure clock: public disclosure, offer for sale, or "
        "sale can start a 12-month US bar and immediately forfeit most foreign rights. "
        "Do not share, sell, or publish this device before filing without counsel.",
        "patient_contact": patient_contact,
    }
    if patient_contact:
        g["stop"] = ("STOP — PATIENT-CONTACTING / POWERED-NEAR-HUMAN DEVICE. Before "
                     "prototyping on or near a person, address: FDA device classification "
                     "and pathway (510(k)/De Novo/PMA); Investigational Device Exemption "
                     "and IRB review (21 CFR 812) for clinical use; biocompatibility of "
                     "materials (ISO 10993) — PLA/PETG/resin prints are generally NOT "
                     "biocompatible as-printed; and electrical safety (IEC 60601) if "
                     "powered. This is a radar, not clearance — consult qualified "
                     "regulatory counsel.")
    return g


def _svg_figure(ctx: dict) -> str:
    dims = ctx.get("dimensions_mm") or {}
    feats = ctx["features"]
    w = 320
    labels = "".join(
        f'<text x="20" y="{70 + i*22}" font-size="12" fill="#333">'
        f'{f["num"]} — {html.escape(f["name"])}</text>'
        for i, f in enumerate(feats)
    )
    dim = (f'{dims.get("x")} × {dims.get("y")} × {dims.get("z")} mm'
           if dims else "see STEP export")
    return (
        f'<svg width="{w}" height="{90 + len(feats)*22}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="170" y="30" width="120" height="80" fill="none" stroke="#222" stroke-width="2"/>'
        f'<line x1="170" y1="30" x2="200" y2="15" stroke="#222"/>'
        f'<line x1="290" y1="30" x2="320" y2="15" stroke="#222"/>'
        f'<line x1="200" y1="15" x2="320" y2="15" stroke="#222"/>'
        f'<line x1="320" y1="15" x2="320" y2="95" stroke="#222"/>'
        f'<line x1="290" y1="110" x2="320" y2="95" stroke="#222"/>'
        f'<text x="230" y="128" font-size="11" fill="#666" text-anchor="middle">FIG. 1 — {dim} (schematic, not to scale)</text>'
        f'<text x="226" y="74" font-size="13" fill="#222" text-anchor="middle">{feats[0]["num"] if feats else 10}</text>'
        f'{labels}</svg>'
    )


def _render_html(ctx: dict, p: dict, figure_svg: str | None = None) -> str:
    s = p["sections"]
    if figure_svg:
        fig = (figure_svg +
               '<div class="muted">FIG. 1 — isometric projection (exact-curve HLR line '
               'art from the model). Overall dimensions are given in the Detailed '
               'Description; numerals are listed under Reference Numerals. Formal '
               'numeral leader-lines and 37 CFR 1.84 shading are a remaining drafting step.</div>')
    else:
        fig = _svg_figure(ctx)
    claims = "".join(f"<li>{html.escape(c)}</li>" for c in s["claims"])
    cov = "".join(
        f"<tr><td>{html.escape(str(r['limitation']))}</td>"
        f"<td>{r['numeral'] if r['numeral'] else '—'}</td>"
        f"<td>{'✓' if r['supported'] else '—'}</td>"
        f"<td>{html.escape(r['where'])}</td></tr>"
        for r in p["coverage"]["rows"])
    checklist = "".join(f"<li>{html.escape(c)}</li>" for c in p["checklist"])
    gaps = "".join(f"<li>{html.escape(g)}</li>" for g in p["coverage"]["gaps"]) \
        or "<li>No automatic gaps detected — counsel must still verify support.</li>"
    g = p["gates"]
    stop = (f'<div class="stop"><strong>{html.escape(g["stop"])}</strong></div>'
            if g.get("stop") else
            '<div class="ok">No patient-contact flag set for this draft. If this device '
            'touches a patient or is powered near a person, regenerate with that flag.</div>')

    def sec(title, txt):
        return f"<h2>{title}</h2><p>{html.escape(txt)}</p>"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(s['title'])} — provisional draft</title>
<style>
body{{font-family:Georgia,serif;max-width:780px;margin:40px auto;padding:0 20px;color:#1a1a1a;line-height:1.6}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}}
.banner{{background:#fff7e6;border:1px solid #d9a441;padding:12px 14px;border-radius:8px;font-size:13px;margin-bottom:8px}}
.clock{{background:#f0f6ff;border:1px solid #6f9fd8;padding:10px 14px;border-radius:8px;font-size:13px}}
.stop{{background:#fdecec;border:1px solid #c0392b;color:#7b241c;padding:12px 14px;border-radius:8px;font-size:13px;margin-top:10px}}
.ok{{background:#eef7ee;border:1px solid #79b779;padding:10px 14px;border-radius:8px;font-size:13px;margin-top:10px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td,th{{border:1px solid #ccc;padding:6px;text-align:left}}
ol,ul{{padding-left:22px}} .fig{{text-align:center;margin:16px 0}} .muted{{color:#777;font-size:12px}}
</style></head><body>
<div class="banner">{html.escape(g['attorney_banner'])}</div>
<div class="clock">{html.escape(g['disclosure_clock'])}</div>
<h1>{html.escape(s['title'])}</h1>
<p class="muted">Provisional patent application — DRAFT. {html.escape(p['ai_note'])}</p>
{sec('Technical Field', s['field'])}
{sec('Background', s['background'])}
{sec('Summary', s['summary'])}
<h2>Brief Description of the Drawings</h2>
<p>FIG. 1 is a view of the device and its principal features.</p>
<div class="fig">{fig}</div>
{sec('Detailed Description', s['detailed_description'])}
<h2>Reference Numerals</h2>
<ul>{''.join(f"<li>{f['num']} — {html.escape(f['name'])}</li>" for f in p['numerals'])}</ul>
<h2>Claims</h2><ol style="list-style:none;padding-left:0">{claims}</ol>
<h2>Abstract</h2><p>{html.escape(s['abstract'])}</p>
<h2>§112(a) Support-Coverage Map</h2>
<table><tr><th>Limitation</th><th>Numeral</th><th>Supported</th><th>Where</th></tr>{cov}</table>
<h3>Coverage gaps to resolve</h3><ul>{gaps}</ul>
<h2>What to do next — filing checklist</h2><ol>{checklist}</ol>
{stop}
<p class="muted" style="margin-top:24px">Generated by Forge as a drafting aid. Not legal advice; not a filing. Have a licensed patent attorney review before any disclosure or filing.</p>
</body></html>"""


def _render_md(p: dict) -> str:
    s = p["sections"]
    g = p["gates"]
    out = [f"> **{g['attorney_banner']}**", "", f"> {g['disclosure_clock']}", "",
           f"# {s['title']}", "", f"*Provisional patent DRAFT. {p['ai_note']}*", "",
           "## Technical Field", s["field"], "", "## Background", s["background"], "",
           "## Summary", s["summary"], "",
           "## Brief Description of the Drawings",
           "FIG. 1 is a schematic view of the device and its principal features.", "",
           "## Detailed Description", s["detailed_description"], "",
           "## Reference Numerals",
           *[f"- {f['num']} — {f['name']}" for f in p["numerals"]], "",
           "## Claims", *s["claims"], "", "## Abstract", s["abstract"], "",
           "## §112(a) Support-Coverage Map",
           "| Limitation | Numeral | Supported | Where |", "|---|---|---|---|",
           *[f"| {r['limitation']} | {r['numeral'] or '—'} | {'yes' if r['supported'] else 'no'} | {r['where']} |"
             for r in p["coverage"]["rows"]], "",
           "## What to do next — filing checklist",
           *[f"{i+1}. {c}" for i, c in enumerate(p["checklist"])], ""]
    if g.get("stop"):
        out += ["## ⚠️ STOP", g["stop"], ""]
    out += ["---", "_Generated by Forge as a drafting aid. Not legal advice; not a filing._"]
    return "\n".join(out)
