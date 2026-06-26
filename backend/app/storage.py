"""Per-project artifact storage on local disk.

Artifacts (STEP/STL) are copied out of the ephemeral sandbox scratch dir into a
durable per-version folder: projects/<project_id>/versions/<version_id>/.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FORGE_DATA_DIR", str(BACKEND_DIR)))
PROJECTS_DIR = DATA_DIR / "projects"

# kind -> filename produced by runner.py
ARTIFACTS = {"step": "part.step", "stl": "part.stl"}


def version_dir(project_id: int, version_id: int) -> Path:
    d = PROJECTS_DIR / str(project_id) / "versions" / str(version_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_artifacts(project_id: int, version_id: int, scratch: str) -> dict:
    src = Path(scratch)
    vd = version_dir(project_id, version_id)
    stored: dict[str, str] = {}
    for kind, fname in ARTIFACTS.items():
        p = src / fname
        if p.exists():
            shutil.copy2(p, vd / fname)
            stored[kind] = fname
    for p in src.glob("view_*.svg"):
        shutil.copy2(p, vd / p.name)
        stored[p.stem] = p.name          # "view_iso" -> "view_iso.svg"
    return stored


def artifact_path(project_id: int, version_id: int, kind: str) -> Path | None:
    fname = ARTIFACTS.get(kind)
    if not fname:
        return None
    p = version_dir(project_id, version_id) / fname
    return p if p.exists() else None


def drawing_path(project_id: int, version_id: int, view: str) -> Path | None:
    p = version_dir(project_id, version_id) / f"view_{view}.svg"
    return p if p.exists() else None
