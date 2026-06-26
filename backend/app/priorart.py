"""Prior-art / novelty aid.

Two modes:
  - No key: generate sensible search terms and deep links to Google Patents,
    Espacenet, and USPTO Patent Public Search so you can search yourself (free).
  - Key on: ai.prior_art_search runs an automated web search (see ai.py).

Per the hardened plan: NEVER assert "novel" — only "no blocking art found in the
sources searched", always paired with what those sources cannot see. A search is
never a legal clearance.
"""
from __future__ import annotations
import urllib.parse

DISCLAIMER = ("A prior-art search is not a legal clearance. Have a patent attorney "
              "or professional searcher confirm novelty before filing or disclosing.")

BLIND_SPOTS = [
    "Foreign-language patents and non-English filings.",
    "Non-patent literature (papers, manuals, catalogs).",
    "Products on the market that were never patented.",
    "Patent applications not yet published (~18-month delay).",
]


def search_terms(ctx: dict) -> list[str]:
    dt = (ctx.get("device_type") or "device").lower()
    feats = [f["name"] for f in ctx.get("features", [])]
    terms = [dt, f"3D printed {dt}"]
    if len(feats) > 1:
        terms.append(f"{dt} {feats[1]}")
    seen, out = set(), []
    for t in terms:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def links(terms: list[str]) -> dict:
    q = terms[0] if terms else "device"
    e = urllib.parse.quote
    return {
        "google_patents": f"https://patents.google.com/?q={e(q)}",
        "espacenet": f"https://worldwide.espacenet.com/patent/search?q={e(q)}",
        "uspto": "https://ppubs.uspto.gov/pubwebapp/",
    }


def deterministic(ctx: dict, error: str | None = None) -> dict:
    terms = search_terms(ctx)
    return {
        "searched": False,
        "queries": terms,
        "links": links(terms),
        "references": [],
        "assessment": ("Run the searches below (Google Patents, Espacenet, USPTO) to check "
                       "for similar patents and products before drafting."),
        "blind_spots": BLIND_SPOTS,
        "disclaimer": DISCLAIMER,
        "error": error,
    }
