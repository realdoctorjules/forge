"""Claude integration (optional — enabled when an Anthropic API key is set).

Two uses, both degrade gracefully to deterministic paths when no key is present:
  1. design_from_prompt — turn free text into a device (archetype + params),
     handling far more natural language than keyword matching.
  2. draft_patent_sections — write the prose sections of a provisional draft.

Per the claude-api reference: model claude-opus-4-8, adaptive thinking for the
harder writing task, robust JSON parsing, and explicit refusal handling.
"""
from __future__ import annotations
import json

from . import config, library

MODEL = "claude-opus-4-8"


def enabled() -> bool:
    return bool(config.get_anthropic_key())


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=config.get_anthropic_key())


def _text(resp) -> str:
    if resp.stop_reason == "refusal":
        raise RuntimeError("model refused the request")
    return "".join(b.text for b in resp.content if b.type == "text")


def _json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # extract the outermost {...} if the model wrapped JSON in prose
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1 and j > i:
            return json.loads(s[i:j + 1])
        raise


def design_from_prompt(prompt: str) -> dict:
    """Return {archetype, params, name, rationale} using the library schema."""
    archs = library.list_archetypes()
    catalog = "\n".join(
        f"- {a['key']}: {a['label']}. params: " +
        ", ".join(f"{k}({v['min']}-{v['max']}{v['unit']})" for k, v in a['params'].items())
        for a in archs
    )
    sys = (
        "You turn a plain-language device request into a parametric device spec, "
        "choosing the closest archetype from a fixed library of SIMPLE RIGID "
        "3D-printable parts, with parameter values within the stated ranges.\n\n"
        "BE HONEST about fit. The library can ONLY make simple rigid parts. If the "
        "request is for something outside that — a wearable/glove/textile/soft good, "
        "an articulated or multi-jointed mechanism, an organic/anatomical shape, an "
        "assembly of many moving parts, a circuit/PCB, or anything that cannot be "
        "genuinely represented by one archetype — you MUST set fit='out_of_scope' and "
        "explain plainly in fit_note what the device actually requires. Use fit='rough' "
        "for a decent-but-imperfect match. Use fit='good' ONLY when an archetype truly "
        "represents the request. Never hide a poor match behind a confident name; if "
        "out_of_scope, name it honestly as a stand-in.\n\n"
        "When fit is 'rough' or 'out_of_scope', ALSO suggest 1-3 related devices that ARE "
        "within this rigid library that the inventor could build instead (e.g., for a glove: "
        "a rigid knuckle guard, a finger splint, a hand-brace bracket) — as 'alternatives', "
        "an array of {label, prompt} where prompt is a short buildable description.\n\n"
        "Respond with ONLY a JSON object, no markdown, with keys: archetype (one of the "
        "library keys), params (object of param->number), name (short), rationale (one "
        "sentence), fit ('good'|'rough'|'out_of_scope'), fit_note (one sentence; '' if good), "
        "alternatives (array of {label, prompt}; [] if fit is good)."
    )
    user = f"Device library:\n{catalog}\n\nRequest: {prompt!r}\n\nReturn the JSON spec."

    resp = _client().messages.create(
        model=MODEL, max_tokens=1500,
        system=sys,
        messages=[{"role": "user", "content": user}],
    )
    data = _json(_text(resp))
    archetype = data.get("archetype")
    if archetype not in library.ARCHETYPES:
        archetype = library.match(prompt)["archetype"]
    params = library.clamp(archetype, data.get("params") or {})
    name = (data.get("name") or "").strip()[:60] or library.ARCHETYPES[archetype]["label"]
    fit = data.get("fit") if data.get("fit") in ("good", "rough", "out_of_scope") else "rough"
    alts = []
    for a in (data.get("alternatives") or [])[:3]:
        if isinstance(a, dict) and a.get("label") and a.get("prompt"):
            alts.append({"label": str(a["label"])[:40], "prompt": str(a["prompt"])[:120]})
    return {"archetype": archetype, "params": params, "name": name,
            "rationale": (data.get("rationale") or "")[:300],
            "fit": fit, "fit_note": (data.get("fit_note") or "")[:300],
            "alternatives": alts, "source": "ai"}


def draft_patent_sections(context: dict) -> dict:
    """Write the prose sections of a provisional patent draft as a JSON object."""
    sys = (
        "You are a patent-drafting assistant helping prepare a DRAFT US provisional "
        "patent application for an inventor's attorney to review. You are not a lawyer "
        "and this is not legal advice. Write clear, specific, enabling prose grounded "
        "ONLY in the provided device facts and reference numerals — never invent test "
        "data, performance claims, or prior art. Respond with ONLY a JSON object, no "
        "markdown, with keys: title, field, background, summary, detailed_description, "
        "claims (array of strings: one independent claim first, then dependent claims), "
        "abstract. In detailed_description, reference features by their numerals."
    )
    user = (
        "Device facts:\n" + json.dumps(context, indent=2) +
        "\n\nWrite the draft sections. Keep the abstract under 150 words. "
        "Claims must be supported by the listed features/parameters."
    )
    resp = _client().messages.create(
        model=MODEL, max_tokens=16000,
        thinking={"type": "adaptive"},
        system=sys,
        messages=[{"role": "user", "content": user}],
    )
    data = _json(_text(resp))
    data["source"] = "ai"
    return data


def prior_art_search(context: dict) -> dict:
    """Automated web prior-art search. Returns structured findings; never asserts
    novelty — only what was found in the sources searched, plus blind spots."""
    from . import priorart
    client = _client()
    search_model = "claude-sonnet-4-6"   # faster than Opus for search+summarize
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}]
    sys = (
        "You are a patent prior-art search assistant. Search the web for existing "
        "patents and commercial products similar to the described device. NEVER "
        "conclude the device is 'novel' or 'patentable' — report only whether you "
        "found similar or overlapping art in the sources you searched, and always "
        "note what those sources cannot see. Respond with ONLY a JSON object with "
        "keys: queries (array of strings you searched), references (array of "
        "{title, url, why_relevant, overlap}), assessment (one of 'no blocking art "
        "found in sources searched' or 'potential overlap found in sources searched', "
        "plus a sentence), blind_spots (array of strings)."
    )
    keep = {k: context[k] for k in ("name", "device_type", "material",
            "dimensions_mm", "features", "params") if k in context}
    messages = [{"role": "user",
                 "content": "Device:\n" + json.dumps(keep, indent=2) +
                 "\n\nSearch for prior art and return the JSON."}]

    resp = client.messages.create(model=search_model, max_tokens=8000, system=sys,
                                  tools=tools, messages=messages)
    guard = 0
    while resp.stop_reason == "pause_turn" and guard < 3:
        messages.append({"role": "assistant", "content": resp.content})
        resp = client.messages.create(model=search_model, max_tokens=8000, system=sys,
                                      tools=tools, messages=messages)
        guard += 1

    data = _json(_text(resp))
    data["searched"] = True
    data["disclaimer"] = priorart.DISCLAIMER
    data.setdefault("references", [])
    data.setdefault("blind_spots", priorart.BLIND_SPOTS)
    data.setdefault("queries", [])
    data.setdefault("assessment", "Search completed; review the references below.")
    return data


def generate_cad_code(prompt: str) -> dict:
    """Generative CAD: the model writes cadquery code for the described device.
    Returns {name, summary, printable_notes, code}. The code runs in the locked
    sandbox (static allowlist + restricted builtins + no network + FS jail)."""
    sys = (
        "You are a mechanical CAD engineer. Write a SHORT Python script using ONLY "
        "`import cadquery as cq` (and optionally `import math`) that builds the requested "
        "device as ONE rigid, 3D-printable solid, assigning the final cadquery Workplane "
        "to a variable named `result`. Use realistic millimetre dimensions.\n"
        "ROBUSTNESS (critical — OCCT fails easily): build the shape as a UNION of simple "
        "primitives (boxes, cylinders, extruded 2D profiles); make holes/openings by "
        "cutting cylinders or shapes straight through; ensure unioned parts overlap so "
        "they truly fuse; AVOID fillets/chamfers unless trivially small; keep it to a "
        "handful of operations; verify the final result is a single solid.\n"
        "Do NOT read or write files; do NOT import anything except cadquery and "
        "math. If the request is a soft/fabric/textile item or otherwise not a single "
        "rigid printable solid, build the closest rigid (or rigid-segmented) printable "
        "interpretation and say so in printable_notes. Respond with ONLY a JSON object: "
        "{name (short), summary (one sentence), printable_notes (what is faithful vs a "
        "compromise), code (the python script as a string)}."
    )
    resp = _client().messages.create(
        model=MODEL, max_tokens=4000, thinking={"type": "adaptive"}, system=sys,
        messages=[{"role": "user", "content": f"Device request: {prompt!r}\n\nReturn the JSON."}],
    )
    data = _json(_text(resp))
    return {
        "name": (data.get("name") or "Generated device")[:60],
        "summary": (data.get("summary") or "")[:300],
        "printable_notes": (data.get("printable_notes") or "")[:500],
        "code": data.get("code") or "",
        "source": "generated",
    }


def edit_params(archetype: str, params: dict, instruction: str) -> dict:
    """Edit-by-chat for a template device: map an instruction to updated params."""
    a = next((x for x in library.list_archetypes() if x["key"] == archetype), None)
    if not a:
        return params
    schema = ", ".join(f"{k}({v['min']}-{v['max']}{v['unit']})" for k, v in a["params"].items())
    sys = (
        "You edit a 3D device's numeric parameters. Given the current parameters and an "
        "instruction, return ONLY JSON {\"params\": {...}} with the updated values. Change "
        "only what the instruction implies; keep the rest. Stay within the given ranges."
    )
    user = (f"Device: {a['label']}\nParameter ranges: {schema}\n"
            f"Current params: {json.dumps(params)}\nInstruction: {instruction!r}\nReturn the JSON.")
    resp = _client().messages.create(model=MODEL, max_tokens=800, system=sys,
                                     messages=[{"role": "user", "content": user}])
    data = _json(_text(resp))
    return library.clamp(archetype, {**params, **(data.get("params") or {})})


def edit_code(code: str, instruction: str) -> dict:
    """Edit-by-chat for a generated device: modify its cadquery script."""
    sys = (
        "You modify a cadquery script per an instruction. The script MUST remain ONE rigid, "
        "3D-printable solid assigned to a variable `result`, using ONLY `import cadquery as cq` "
        "and optionally `import math`. Keep changes minimal and robust (avoid fragile ops). "
        "Respond with ONLY JSON: {name (short), summary (one sentence), code (the full updated script)}."
    )
    user = f"Current script:\n{code}\n\nInstruction: {instruction!r}\n\nReturn the JSON."
    resp = _client().messages.create(model=MODEL, max_tokens=4000, thinking={"type": "adaptive"},
                                     system=sys, messages=[{"role": "user", "content": user}])
    data = _json(_text(resp))
    return {"name": (data.get("name") or "Edited device")[:60],
            "summary": (data.get("summary") or "")[:300],
            "code": data.get("code") or code}


def fix_code(code: str, error: str) -> dict:
    """Repair loop: given failing cadquery code + the error, return fixed code."""
    sys = (
        "A cadquery script failed to build (error/traceback below). Rewrite it so it "
        "BUILDS and produces ONE rigid 3D-printable solid assigned to `result`, using "
        "ONLY `import cadquery as cq` and optionally `import math`. Prefer ROBUST ops: "
        "build the shape as a union of simple primitives; AVOID fillets/chamfers (or make "
        "radii far smaller than the feature); make holes with simple cylinders cut through; "
        "ensure overlapping unions actually intersect. Keep the same overall design intent. "
        "Respond with ONLY JSON: {name (short), summary (one sentence), code (full script)}."
    )
    user = f"Script:\n{code}\n\nError / traceback:\n{error[:1500]}\n\nReturn the fixed JSON."
    resp = _client().messages.create(model=MODEL, max_tokens=4000, thinking={"type": "adaptive"},
                                     system=sys, messages=[{"role": "user", "content": user}])
    data = _json(_text(resp))
    return {"name": (data.get("name") or "Repaired device")[:60],
            "summary": (data.get("summary") or "")[:300],
            "code": data.get("code") or code}
