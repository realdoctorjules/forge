# Forge

A single-user R&D web app: take an idea (or a 3D model) → a 3D device → know
what it's made of (BOM / material / dimensions / weight / cost / how to print) →
export (3D / 2D / patent figures) → an **attorney-review-ready** patent draft.

> Not a law firm, not a filing. Patent output is a draft for a licensed
> attorney to review and file. Nothing here is legal or regulatory advice.

## Where we are: P0 (foundations)

The hardened, value-first plan (after an 11-agent red-team review) is:

| Phase | What | Gate |
|-------|------|------|
| **P0** | Foundations: viewport, isolated CAD worker, versioning | ← we are here |
| **P-A** | **MVP** — import a STEP, produce an attorney-review-ready patent package | attorney says "usable starting point"? |
| **SPIKE-1** | Can the LLM author parametric CAD reliably? | ≥60% spec-conformant in 3 tries, else ship STEP-in only |
| **P-B** | Prompt → parametric model (only if SPIKE-1 passes) | |
| **P-C** | Slicer-grounded manufacturing & analysis | |
| **P-D** | Enrichments | |

### What P0 proves
- A parametric part round-trips through an **isolated** worker → STEP + STL → 3D viewport.
- A deliberately-injected **native crash (SIGSEGV)** is caught and attributed to a
  specific CAD operation **without killing the backend**.
- A **parameter change produces a committed, diffable version** (git-like history).

### Worker isolation (honest scope)
The CAD worker runs as a **separate OS process** under macOS `sandbox-exec` with:
- **network egress denied** (verified: outbound sockets are blocked),
- **filesystem writes jailed** to a per-run scratch dir (verified: writes elsewhere blocked),
- a hard wall-clock **timeout** → SIGKILL the process group (catches OCCT hangs),
- **signal-level crash detection** (SIGSEGV/SIGABRT) with per-op attribution,
- a static **AST import-allowlist** for the LLM-authored code arriving in P-B.

`sandbox-exec` is macOS-only and Apple-deprecated. The production target is a
network-egress-denied, read-only-rootfs **container** — a tracked P0+ hardening.
On a host without `sandbox-exec`, the worker falls back to subprocess + timeout +
crash-detection + allowlist, but **without** kernel-enforced network/FS confinement
(reported via `/api/selftest/isolation`).

## Run it

Backend (FastAPI, port 8000):
```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (Vite, port 5173):
```bash
cd frontend
npm run dev
```

### Self-tests (P0 exit criteria)
```bash
curl localhost:8000/api/selftest/isolation
curl -X POST localhost:8000/api/selftest/segfault
curl -X POST localhost:8000/api/selftest/allowlist
```

## Stack
- Frontend: React + Vite + TypeScript, react-three-fiber + drei, Zustand.
- Backend: Python FastAPI; CadQuery / OpenCASCADE (OCCT) for geometry.
- CAD authoring: the LLM emits **parametric code**, never meshes (P-B).
- Storage: SQLite version DAG + per-project artifact folders + an
  inventorship log (who specified what vs. what the machine generated).
