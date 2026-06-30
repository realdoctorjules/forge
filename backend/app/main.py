"""Forge backend.

Pipeline: prompt/params/STEP -> isolated CAD worker -> geometry -> analysis
(material/weight/cost/BOM) -> durable per-version storage -> SQLite version DAG
+ inventorship log.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import uuid
from pathlib import Path

# Low-memory mode: skip the resident warm worker (one CAD process at a time) and
# render a single drawing view. FORGE_LOWMEM forces it on ("1") or off ("0"/"");
# when unset we auto-detect from total RAM so a tier upgrade unlocks full speed
# (warm-worker live preview + 4 drawing views) with no config change.
def _auto_lowmem() -> bool:
    env = os.environ.get("FORGE_LOWMEM")
    if env is not None:
        return env.strip().lower() not in ("", "0", "false", "no", "off")
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) < 1_200_000  # < ~1.2 GB -> lean
    except Exception:
        pass
    return False


LOWMEM = _auto_lowmem()
# Propagate the resolved decision to CAD subprocesses (they read the env var).
os.environ["FORGE_LOWMEM"] = "1" if LOWMEM else ""

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import ai, components, config, db, drawings, library, patent, priorart, regulatory, slicer, storage


def _apply_slicer(a: dict, est: dict) -> None:
    """Overwrite a heuristic analysis with real PrusaSlicer numbers."""
    a["mass_g"] = est["filament_g"]
    a["mass_g_range"] = [round(est["filament_g"] * 0.92, 1), round(est["filament_g"] * 1.08, 1)]
    a["print_time_h"] = est["print_time_h"]
    a["print_time_str"] = est.get("print_time_str")
    a["print_time_h_range"] = [round(est["print_time_h"] * 0.9, 2), round(est["print_time_h"] * 1.15, 2)]
    if est.get("cost_usd") is not None:
        a["cost_usd"] = round(est["cost_usd"] + a.get("parts_cost_usd", 0), 2)
        a["cost_usd_range"] = [round(a["cost_usd"] * 0.9, 2), round(a["cost_usd"] * 1.15, 2)]
    a["slicer_source"] = est["source"]
    a["confidence"] = ("Sliced with PrusaSlicer — realistic estimate at default settings "
                       "(0.2 mm, 20% infill); your printer/material/supports may differ.")


def _slice_into(analysis, scratch, material) -> None:
    if analysis and slicer.available():
        est = slicer.slice_estimate(Path(scratch) / "part.stl", material)
        if est:
            _apply_slicer(analysis, est)
from .worker import isolation
from .worker.import_allowlist import scan_source

app = FastAPI(title="Forge", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


class CreateProject(BaseModel):
    name: str
    device_family: str | None = None


class PromptRequest(BaseModel):
    prompt: str
    material: str | None = None


class GenerateRequest(BaseModel):
    archetype: str
    params: dict = {}
    material: str | None = None
    label: str | None = None


# --- core build helper ----------------------------------------------------

def _build_and_store(pid: int, *, archetype: str, params: dict, material: str,
                     name: str, label: str, prompt: str | None = None,
                     import_step: str | None = None) -> dict:
    parent = db.latest_version(pid)

    db.add_log(project_id=pid, version_id=None, actor="human",
               action="prompt" if prompt else "adjust_parameters",
               detail={"prompt": prompt, "archetype": archetype, "params": params})

    if import_step:
        res = isolation.run_part(import_step=import_step, timeout_s=60.0)
    elif LOWMEM:  # one process at a time — no resident warm worker
        res = isolation.run_part(library.module_name(archetype), params, timeout_s=60.0)
    else:
        try:  # warm worker = fast; on death fall back to the one-shot isolated runner
            res = isolation.warm_run(library.module_name(archetype), params,
                                     full=True, timeout_s=45.0)
        except isolation.WarmError:
            res = isolation.run_part(library.module_name(archetype), params, timeout_s=45.0)

    ok = res["ok"]
    geometry = (res.get("result") or {}).get("metrics") if ok else None
    analysis = None
    if ok and geometry:
        analysis = library.analyze(
            geometry["volume_mm3"], material, library.standard_parts(archetype)
            if archetype in library.ARCHETYPES else [])
        _slice_into(analysis, res["scratch"], material)

    dfm = (library.dfm_check(archetype, params, geometry)
           if ok and geometry and archetype in library.ARCHETYPES else None)
    metrics = {
        "geometry": geometry, "analysis": analysis, "dfm": dfm,
        "archetype": archetype,
        "archetype_label": (library.ARCHETYPES[archetype]["label"]
                            if archetype in library.ARCHETYPES else "Imported STEP"),
        "material": material, "name": name, "prompt": prompt,
    } if ok else None

    ver = db.create_version(
        project_id=pid, parent_id=parent["id"] if parent else None,
        part_module=archetype, params=params,
        status="ok" if ok else "failed",
        metrics=metrics, crash=res.get("crash"), files=None,
        sandboxed=res["sandboxed"], label=label or name,
    )

    files = {}
    if ok:
        files = storage.store_artifacts(pid, ver["id"], res["scratch"])
        with db.connect() as conn:
            conn.execute("UPDATE versions SET files_json=? WHERE id=?",
                         (json.dumps(files), ver["id"]))

    db.add_log(project_id=pid, version_id=ver["id"], actor="system",
               action="build_geometry",
               detail={"status": ver["status"], "last_op": res["last_op"],
                       "sandboxed": res["sandboxed"], "crash": res.get("crash")})

    return {
        "version": db.get_version(ver["id"]),
        "ok": ok,
        "crash": res.get("crash"),
        "last_op": res["last_op"],
        "sandboxed": res["sandboxed"],
        "elapsed_s": res["elapsed_s"],
        "files": {k: f"/api/versions/{ver['id']}/file/{k}" for k in files},
        "stderr_tail": res["stderr_tail"] if not ok else "",
    }


# --- meta ------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/library")
def get_library() -> dict:
    return {"archetypes": library.list_archetypes(), "materials": library.list_materials()}


# --- projects --------------------------------------------------------------

@app.post("/api/projects")
def create_project(body: CreateProject) -> dict:
    proj = db.create_project(body.name, body.device_family)
    db.add_log(project_id=proj["id"], version_id=None, actor="human",
               action="create_project", detail={"name": body.name})
    return proj


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return db.list_projects()


class ProjectName(BaseModel):
    name: str


@app.post("/api/projects/{pid}/name")
def rename_project(pid: int, body: ProjectName) -> dict:
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    db.set_project_name(pid, body.name.strip()[:80] or "Untitled device")
    return {"ok": True}


@app.delete("/api/projects/{pid}")
def remove_project(pid: int) -> dict:
    import shutil
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    db.delete_project(pid)
    shutil.rmtree(storage.PROJECTS_DIR / str(pid), ignore_errors=True)
    return {"ok": True}


@app.get("/api/projects/{pid}/versions")
def list_versions(pid: int) -> list[dict]:
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    return db.list_versions(pid)


@app.get("/api/projects/{pid}/log")
def project_log(pid: int) -> list[dict]:
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    return db.list_log(pid)


@app.post("/api/projects/{pid}/prompt")
def build_from_prompt(pid: int, body: PromptRequest) -> dict:
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    used_ai = False
    if ai.enabled():
        try:
            m = ai.design_from_prompt(body.prompt)
            used_ai = True
        except Exception:  # noqa: BLE001 — fall back to keyword matching
            m = library.match(body.prompt)
    else:
        m = library.match(body.prompt)
    material = body.material or getattr(
        library.ARCHETYPES[m["archetype"]]["mod"], "DEFAULT_MATERIAL", "PLA")
    out = _build_and_store(pid, archetype=m["archetype"], params=m["params"],
                           material=material, name=m["name"], label=m["name"],
                           prompt=body.prompt)
    out["matched"] = {"archetype": m["archetype"], "used_ai": used_ai,
                      "rationale": m.get("rationale", ""),
                      "fit": m.get("fit", "good"), "fit_note": m.get("fit_note", ""),
                      "alternatives": m.get("alternatives", [])}
    return out


# --- AI settings -----------------------------------------------------------

class KeyRequest(BaseModel):
    key: str


@app.get("/api/ai-status")
def ai_status() -> dict:
    return {"enabled": ai.enabled(), "model": ai.MODEL}


@app.post("/api/settings/anthropic-key")
def set_key(body: KeyRequest) -> dict:
    config.set_anthropic_key(body.key)
    return {"enabled": ai.enabled()}


# --- patent ----------------------------------------------------------------

class PatentRequest(BaseModel):
    patient_contact: bool = False


@app.post("/api/versions/{vid}/patent")
def make_patent(vid: int, body: PatentRequest) -> dict:
    v = db.get_version(vid)
    if not v or v["status"] != "ok":
        raise HTTPException(404, "no buildable version")
    payload = patent.build(v, patient_contact=body.patient_contact)
    db.add_log(project_id=v["project_id"], version_id=vid, actor="system",
               action="generate_patent_draft",
               detail={"source": payload["sections"]["source"],
                       "patient_contact": body.patient_contact})
    return payload


@app.get("/api/versions/{vid}/patent.html")
def patent_html(vid: int):
    v = db.get_version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    p = storage.version_dir(v["project_id"], vid) / "patent.html"
    if not p.exists():
        raise HTTPException(404, "no patent draft yet — generate one first")
    return FileResponse(str(p), media_type="text/html")


@app.get("/api/versions/{vid}/patent.md")
def patent_md(vid: int):
    v = db.get_version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    p = storage.version_dir(v["project_id"], vid) / "patent.md"
    if not p.exists():
        raise HTTPException(404, "no patent draft yet — generate one first")
    return FileResponse(str(p), media_type="text/markdown",
                        filename=f"forge_v{vid}_provisional_draft.md")


# --- 2D technical drawings -------------------------------------------------

@app.get("/api/versions/{vid}/drawing-sheet.html")
def drawing_sheet(vid: int):
    from fastapi.responses import HTMLResponse
    v = db.get_version(vid)
    if not v or v["status"] != "ok" or not (v.get("metrics") or {}).get("geometry"):
        raise HTTPException(404, "no buildable version")
    return HTMLResponse(drawings.build_sheet(v))


@app.get("/api/versions/{vid}/drawing/{view}.svg")
def drawing(vid: int, view: str):
    v = db.get_version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    p = storage.drawing_path(v["project_id"], vid, view)
    if not p:
        raise HTTPException(404, f"no {view} view for this version")
    return FileResponse(str(p), media_type="image/svg+xml")


# --- prior art -------------------------------------------------------------

# Background AI prior-art searches. The button returns instant search links right
# away and (if a key is set) kicks off ai.prior_art_search on a worker thread; the
# frontend polls /api/prior-art/jobs/{id} for the found references. Keeps the slow,
# flaky agentic web search off the request path.
_PA_JOBS: dict = {}
_PA_LOCK = threading.Lock()


def _pa_run(job_id: str, ctx: dict) -> None:
    try:
        data = ai.prior_art_search(ctx)
        with _PA_LOCK:
            _PA_JOBS[job_id] = {"status": "done", "result": data}
    except Exception as e:  # noqa: BLE001
        with _PA_LOCK:
            _PA_JOBS[job_id] = {"status": "error", "error": str(e)[:300]}


@app.post("/api/versions/{vid}/prior-art")
def prior_art(vid: int) -> dict:
    v = db.get_version(vid)
    if not v or v["status"] != "ok":
        raise HTTPException(404, "no buildable version")
    ctx = patent._context(v)
    payload = priorart.deterministic(ctx)  # instant: curated links + search terms
    if ai.enabled():
        job_id = uuid.uuid4().hex
        with _PA_LOCK:
            if len(_PA_JOBS) > 40:  # bound the in-memory store
                for k in list(_PA_JOBS)[:20]:
                    _PA_JOBS.pop(k, None)
            _PA_JOBS[job_id] = {"status": "searching"}
        threading.Thread(target=_pa_run, args=(job_id, ctx), daemon=True).start()
        payload["ai_job"] = job_id
        payload["ai_searching"] = True
    else:
        payload["ai_searching"] = False
    return payload


@app.get("/api/prior-art/jobs/{job_id}")
def prior_art_job(job_id: str) -> dict:
    with _PA_LOCK:
        job = _PA_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job


@app.post("/api/projects/{pid}/preview")
def preview(pid: int, body: GenerateRequest) -> dict:
    """Fast, ephemeral STL build for live slider dragging — no version committed."""
    if body.archetype not in library.ARCHETYPES:
        raise HTTPException(400, "unknown archetype")
    params = library.clamp(body.archetype, body.params or {})
    material = body.material or getattr(
        library.ARCHETYPES[body.archetype]["mod"], "DEFAULT_MATERIAL", "PLA")
    if LOWMEM:
        res = isolation.run_part(library.module_name(body.archetype), params, timeout_s=30.0)
    else:
        try:
            res = isolation.warm_run(library.module_name(body.archetype), params,
                                     full=False, timeout_s=20.0)
        except isolation.WarmError:
            res = isolation.run_part(library.module_name(body.archetype), params, timeout_s=30.0)
    if not res["ok"]:
        return {"ok": False, "error": (res.get("stderr_tail") or "build failed")[:200],
                "crash": res.get("crash")}
    geom = res["result"]["metrics"]
    analysis = library.analyze(geom["volume_mm3"], material,
                               library.standard_parts(body.archetype))
    dfm = library.dfm_check(body.archetype, params, geom)
    stl = (Path(res["scratch"]) / "part.stl").read_bytes()
    return {"ok": True, "geometry": geom, "analysis": analysis, "dfm": dfm,
            "stl_b64": base64.b64encode(stl).decode()}


@app.post("/api/projects/{pid}/generate")
def generate(pid: int, body: GenerateRequest) -> dict:
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    if body.archetype not in library.ARCHETYPES:
        raise HTTPException(400, "unknown archetype")
    params = library.clamp(body.archetype, body.params or {})
    material = body.material or getattr(
        library.ARCHETYPES[body.archetype]["mod"], "DEFAULT_MATERIAL", "PLA")
    name = library.ARCHETYPES[body.archetype]["label"]
    return _build_and_store(pid, archetype=body.archetype, params=params,
                            material=material, name=name, label=body.label or name)


class InventRequest(BaseModel):
    prompt: str
    material: str | None = None


def _build_generated(pid: int, *, name: str, summary: str, printable_notes: str,
                     code: str, material: str, prompt: str, parent: dict | None) -> dict:
    """Safety-scan + sandbox-run AI geometry code, store as a generated version.
    Shared by /invent and /edit (generated case)."""
    res = None
    for _attempt in range(3):  # first try + up to 2 AI repairs on build failure
        issues = scan_source(code, allow_modules={"cadquery", "cq", "math"})
        if issues:
            return {"ok": False, "error": "Generated code was blocked by the safety allowlist: "
                    + "; ".join(issues), "matched": {"generated": True}}
        res = isolation.run_part(generated_code=code, timeout_s=60.0)
        if res["ok"] or not ai.enabled():
            break
        err = ((res.get("result") or {}).get("trace")
               or (res.get("result") or {}).get("error")
               or "the build produced no valid solid (likely an OpenCASCADE failure)")
        try:
            fixed = ai.fix_code(code, err)
            code, name = fixed["code"], (fixed.get("name") or name)
            summary = fixed.get("summary") or summary
        except Exception:  # noqa: BLE001
            break
    ok = res["ok"]
    geometry = (res.get("result") or {}).get("metrics") if ok else None
    analysis = library.analyze(geometry["volume_mm3"], material, []) if ok and geometry else None
    _slice_into(analysis, res["scratch"], material)
    dfm = library.dfm_check("generated", {}, geometry) if ok and geometry else None
    metrics = {
        "geometry": geometry, "analysis": analysis, "dfm": dfm,
        "archetype": "generated", "archetype_label": name,
        "material": material, "name": name, "prompt": prompt,
        "generated": True, "summary": summary,
        "printable_notes": printable_notes, "generated_code": code,
    } if ok else None
    ver = db.create_version(
        project_id=pid, parent_id=parent["id"] if parent else None,
        part_module="generated", params={}, status="ok" if ok else "failed",
        metrics=metrics, crash=res.get("crash"), files=None,
        sandboxed=res["sandboxed"], label=name)
    files = {}
    if ok:
        files = storage.store_artifacts(pid, ver["id"], res["scratch"])
        (storage.version_dir(pid, ver["id"]) / "generated_code.py").write_text(code)
        with db.connect() as conn:
            conn.execute("UPDATE versions SET files_json=? WHERE id=?",
                         (json.dumps(files), ver["id"]))
    db.add_log(project_id=pid, version_id=ver["id"], actor="system",
               action="generate_geometry", detail={"status": ver["status"]})
    return {
        "version": db.get_version(ver["id"]), "ok": ok,
        "matched": {"generated": True, "used_ai": True, "archetype": "generated",
                    "fit": "good", "fit_note": "", "alternatives": [],
                    "summary": summary, "printable_notes": printable_notes},
        "files": {k: f"/api/versions/{ver['id']}/file/{k}" for k in files},
        "error": ((res.get("result") or {}).get("error") or "geometry failed to build")
                 if not ok else "",
        "crash": res.get("crash"),
    }


@app.post("/api/projects/{pid}/invent")
def invent(pid: int, body: InventRequest) -> dict:
    """Generative CAD: AI writes geometry code for ANY rigid device."""
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    if not ai.enabled():
        raise HTTPException(400, "AI key required for generative CAD")
    db.add_log(project_id=pid, version_id=None, actor="human", action="invent",
               detail={"prompt": body.prompt})
    try:
        gen = ai.generate_cad_code(body.prompt)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"generation failed: {e}")
    return _build_generated(pid, name=gen["name"], summary=gen["summary"],
                            printable_notes=gen["printable_notes"], code=gen["code"],
                            material=body.material or "PLA", prompt=body.prompt,
                            parent=db.latest_version(pid))


class EditRequest(BaseModel):
    instruction: str
    base_version_id: int | None = None


@app.post("/api/projects/{pid}/edit")
def edit(pid: int, body: EditRequest) -> dict:
    """Edit-by-chat: 'make the wall thicker', 'add 2 compartments'. Tweaks the
    current version's params (template) or its code (generated) -> a new version."""
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    if not ai.enabled():
        raise HTTPException(400, "AI key required for edit-by-chat")
    base = db.get_version(body.base_version_id) if body.base_version_id else db.latest_version(pid)
    if not base or base["status"] != "ok" or not base.get("metrics"):
        raise HTTPException(404, "no editable base version")
    m = base["metrics"]
    db.add_log(project_id=pid, version_id=None, actor="human", action="edit",
               detail={"instruction": body.instruction, "base": base["id"]})

    if m.get("generated") and m.get("generated_code"):
        try:
            gen = ai.edit_code(m["generated_code"], body.instruction)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"edit failed: {e}")
        return _build_generated(pid, name=gen["name"], summary=gen["summary"],
                                printable_notes="Edited: " + body.instruction, code=gen["code"],
                                material=m.get("material", "PLA"),
                                prompt=f"[edit] {body.instruction}", parent=base)

    archetype = m.get("archetype")
    if archetype not in library.ARCHETYPES:
        raise HTTPException(400, "this device can't be edited by chat")
    try:
        new_params = ai.edit_params(archetype, base.get("params") or {}, body.instruction)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"edit failed: {e}")
    return _build_and_store(pid, archetype=archetype, params=new_params,
                            material=m.get("material", "PLA"),
                            name=m.get("name") or library.ARCHETYPES[archetype]["label"],
                            label=m.get("name") or library.ARCHETYPES[archetype]["label"],
                            prompt=f"[edit] {body.instruction}")


@app.post("/api/projects/{pid}/import-step")
async def import_step(pid: int, file: UploadFile = File(...)) -> dict:
    if not db.get_project(pid):
        raise HTTPException(404, "project not found")
    uploads = storage.PROJECTS_DIR / str(pid) / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / (file.filename or "upload.step")
    dest.write_bytes(await file.read())
    name = f"Imported · {file.filename}"
    return _build_and_store(pid, archetype="imported", params={}, material="PLA",
                            name=name, label=name, import_step=str(dest))


# --- versions --------------------------------------------------------------

@app.get("/api/versions/{vid}")
def get_version(vid: int) -> dict:
    v = db.get_version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    return v


@app.get("/api/versions/{vid}/analysis")
def recompute_analysis(vid: int, material: str) -> dict:
    """Instant re-cost in a different material from the stored geometry volume."""
    v = db.get_version(vid)
    if not v or not v.get("metrics") or not v["metrics"].get("geometry"):
        raise HTTPException(404, "no geometry for this version")
    archetype = v["metrics"].get("archetype", "imported")
    std = library.standard_parts(archetype) if archetype in library.ARCHETYPES else []
    return library.analyze(v["metrics"]["geometry"]["volume_mm3"], material, std)


@app.get("/api/versions/{vid}/file/{kind}")
def get_version_file(vid: int, kind: str):
    v = db.get_version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    p = storage.artifact_path(v["project_id"], vid, kind)
    if not p:
        raise HTTPException(404, f"no {kind} artifact for this version")
    return FileResponse(str(p), media_type="application/octet-stream",
                        filename=f"forge_v{vid}.{kind}")


@app.get("/api/versions/diff")
def diff(a: int, b: int) -> dict:
    return db.diff_versions(a, b)


# --- annotations + labels (iteration tools) --------------------------------

class AnnotationRequest(BaseModel):
    x: float
    y: float
    z: float
    text: str


class LabelRequest(BaseModel):
    label: str


# --- electronics fit ------------------------------------------------------

class FitRequest(BaseModel):
    component: str
    clearance_min: float = 1.5


def _interior(v: dict):
    m = v.get("metrics") or {}
    arch = m.get("archetype")
    p = v.get("params") or {}
    bb = (m.get("geometry") or {}).get("bbox_mm") or {}
    if arch in ("enclosure", "tray") and all(k in p for k in ("width", "depth", "height", "wall")):
        wall = p["wall"]
        return {"l": p["width"] - 2 * wall, "w": p["depth"] - 2 * wall, "h": p["height"] - wall}, True
    if arch == "cap" and all(k in p for k in ("diameter", "height", "wall")):
        wall = p["wall"]
        return {"l": p["diameter"] - 2 * wall, "w": p["diameter"] - 2 * wall, "h": p["height"] - wall}, True
    return {"l": bb.get("x", 0), "w": bb.get("y", 0), "h": bb.get("z", 0)}, False


@app.get("/api/components")
def get_components() -> list[dict]:
    return components.list_components()


# --- regulatory radar -----------------------------------------------------

@app.get("/api/regulatory/questions")
def regulatory_questions() -> list[dict]:
    return regulatory.questions()


class RegulatoryRequest(BaseModel):
    answers: dict = {}


@app.post("/api/regulatory/assess")
def regulatory_assess(body: RegulatoryRequest) -> dict:
    return regulatory.assess(body.answers)


@app.post("/api/versions/{vid}/fit-check")
def fit_check(vid: int, body: FitRequest) -> dict:
    v = db.get_version(vid)
    if not v or not (v.get("metrics") or {}).get("geometry"):
        raise HTTPException(404, "no buildable version")
    interior, is_cavity = _interior(v)
    res = components.fit_check(interior, body.component, body.clearance_min)
    res["is_cavity"] = is_cavity
    if not is_cavity:
        res["warnings"] = ["Checked against the OVERALL size, not a verified hollow cavity "
                           "— only meaningful if this part is actually hollow."] + res.get("warnings", [])
    return res


@app.get("/api/versions/{vid}/annotations")
def get_annotations(vid: int) -> list[dict]:
    return db.list_annotations(vid)


@app.post("/api/versions/{vid}/annotations")
def add_annotation(vid: int, body: AnnotationRequest) -> dict:
    v = db.get_version(vid)
    if not v:
        raise HTTPException(404, "version not found")
    return db.add_annotation(vid, body.x, body.y, body.z, body.text)


@app.delete("/api/annotations/{aid}")
def delete_annotation(aid: int) -> dict:
    db.delete_annotation(aid)
    return {"ok": True}


@app.post("/api/versions/{vid}/label")
def set_label(vid: int, body: LabelRequest) -> dict:
    if not db.get_version(vid):
        raise HTTPException(404, "version not found")
    db.set_version_label(vid, body.label.strip()[:80])
    return {"ok": True}


# --- self-tests (P0 isolation exit criteria) -------------------------------

@app.get("/api/selftest/isolation")
def selftest_isolation() -> dict:
    return {
        "sandbox_available": isolation.SANDBOX_EXEC is not None,
        "sandbox_kind": "macos-sandbox-exec" if isolation.SANDBOX_EXEC else "subprocess-only",
        "note": "Network egress is denied and writes are jailed to scratch via sandbox-exec.",
    }


@app.post("/api/selftest/segfault")
def selftest_segfault() -> dict:
    res = isolation.run_part("hello_enclosure", library.defaults("enclosure"),
                             timeout_s=30.0, simulate_crash_op="shell_open_top")
    return {
        "backend_alive": True,
        "child_returncode": res["returncode"],
        "crash": res["crash"],
        "op_trace": res["op_trace"],
        "interpretation": (
            f"child killed by {res['crash']['signal']} attributed to op "
            f"'{res['crash']['attributed_op']}'" if res.get("crash") else "no crash detected"),
    }


class AllowlistCheck(BaseModel):
    source: str = "import os\nos.system('rm -rf /')\n"


@app.post("/api/selftest/allowlist")
def selftest_allowlist(body: AllowlistCheck = AllowlistCheck()) -> dict:
    issues = scan_source(body.source)
    return {"rejected": bool(issues), "issues": issues}


# --- serve the built frontend (production / Render: one service) -----------
# In dev, the frontend runs on Vite (5173) so FORGE_FRONTEND_DIST is unset and
# this is skipped. In the Docker image it points at the built /app/frontend_dist,
# and FastAPI serves the SPA at "/" while /api/* routes above take precedence.
import os as _os
from fastapi.staticfiles import StaticFiles as _StaticFiles

_dist = _os.environ.get("FORGE_FRONTEND_DIST")
if _dist and _os.path.isdir(_dist):
    app.mount("/", _StaticFiles(directory=_dist, html=True), name="frontend")
