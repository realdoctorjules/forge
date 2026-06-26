"""SQLite source-of-truth + git-like version history.

LOCKED source-of-truth model (P0):
  - A version's authoritative content = (part module + named parameter set).
  - Each generate creates an immutable version row with a parent pointer and a
    content_hash, so history is a diffable DAG of parameter/code revisions.
  - The inventorship_log records WHO did WHAT (human specified/chose vs. machine
    generated) - dated conception evidence + AI-inventorship support, at near
    zero cost. This is the schema the patent module builds on later.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
# FORGE_DATA_DIR lets the cloud deploy point storage at a persistent disk.
DATA_DIR = Path(os.environ.get("FORGE_DATA_DIR", str(BACKEND_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "forge.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    device_family TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS versions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id),
    parent_id    INTEGER REFERENCES versions(id),
    label        TEXT,
    part_module  TEXT NOT NULL,
    params_json  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status       TEXT NOT NULL,           -- ok | failed
    metrics_json TEXT,
    crash_json   TEXT,
    files_json   TEXT,
    sandboxed    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventorship_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    version_id  INTEGER REFERENCES versions(id),
    actor       TEXT NOT NULL,            -- human | model | system
    action      TEXT NOT NULL,
    detail_json TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL REFERENCES versions(id),
    x          REAL NOT NULL,
    y          REAL NOT NULL,
    z          REAL NOT NULL,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def content_hash(part_module: str, params: dict) -> str:
    blob = json.dumps({"part": part_module, "params": params}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


# --- projects -------------------------------------------------------------

def create_project(name: str, device_family: str | None = None) -> dict:
    # Read back on the SAME connection: the insert's transaction is not committed
    # until this `with` block exits, so a second connection would not see the row.
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, device_family, created_at) VALUES (?,?,?)",
            (name, device_family, now()),
        )
        row = conn.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def get_project(pid: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None


def list_projects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


# --- versions -------------------------------------------------------------

def create_version(*, project_id: int, parent_id: int | None, part_module: str,
                    params: dict, status: str, metrics: dict | None,
                    crash: dict | None, files: dict | None, sandboxed: bool,
                    label: str | None = None) -> dict:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO versions
               (project_id, parent_id, label, part_module, params_json, content_hash,
                status, metrics_json, crash_json, files_json, sandboxed, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (project_id, parent_id, label, part_module, json.dumps(params),
             content_hash(part_module, params), status,
             json.dumps(metrics) if metrics else None,
             json.dumps(crash) if crash else None,
             json.dumps(files) if files else None,
             1 if sandboxed else 0, now()),
        )
        row = conn.execute("SELECT * FROM versions WHERE id=?", (cur.lastrowid,)).fetchone()
        return _hydrate(row)


def _hydrate(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k_src, k_dst in [("params_json", "params"), ("metrics_json", "metrics"),
                         ("crash_json", "crash"), ("files_json", "files")]:
        d[k_dst] = json.loads(d[k_src]) if d.get(k_src) else None
        d.pop(k_src, None)
    d["sandboxed"] = bool(d.get("sandboxed"))
    return d


def get_version(vid: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
        return _hydrate(row) if row else None


def list_versions(project_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM versions WHERE project_id=? ORDER BY id DESC", (project_id,)
        ).fetchall()
        return [_hydrate(r) for r in rows]


def latest_version(project_id: int) -> dict | None:
    vs = list_versions(project_id)
    return vs[0] if vs else None


def diff_versions(a_id: int, b_id: int) -> dict:
    a, b = get_version(a_id), get_version(b_id)
    if not a or not b:
        return {"error": "version not found"}
    pa, pb = a["params"] or {}, b["params"] or {}
    changes = {}
    for key in sorted(set(pa) | set(pb)):
        if pa.get(key) != pb.get(key):
            changes[key] = {"from": pa.get(key), "to": pb.get(key)}
    return {
        "from_version": a_id, "to_version": b_id,
        "code_changed": a["content_hash"] != b["content_hash"] and a["part_module"] != b["part_module"],
        "param_changes": changes,
    }


# --- inventorship ---------------------------------------------------------

def add_log(*, project_id: int, version_id: int | None, actor: str,
            action: str, detail: dict | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO inventorship_log
               (project_id, version_id, actor, action, detail_json, created_at)
               VALUES (?,?,?,?,?,?)""",
            (project_id, version_id, actor, action,
             json.dumps(detail) if detail else None, now()),
        )


def list_log(project_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM inventorship_log WHERE project_id=? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d["detail_json"]) if d.get("detail_json") else None
            d.pop("detail_json", None)
            out.append(d)
        return out


# --- annotations + labels -------------------------------------------------

def add_annotation(version_id: int, x: float, y: float, z: float, text: str) -> dict:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO annotations (version_id, x, y, z, text, created_at) VALUES (?,?,?,?,?,?)",
            (version_id, x, y, z, text, now()))
        row = conn.execute("SELECT * FROM annotations WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_annotations(version_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM annotations WHERE version_id=? ORDER BY id ASC", (version_id,)).fetchall()
        return [dict(r) for r in rows]


def delete_annotation(aid: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM annotations WHERE id=?", (aid,))


def set_version_label(vid: int, label: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE versions SET label=? WHERE id=?", (label, vid))


def set_project_name(pid: int, name: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE projects SET name=? WHERE id=?", (name, pid))


def delete_project(pid: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM annotations WHERE version_id IN "
                     "(SELECT id FROM versions WHERE project_id=?)", (pid,))
        conn.execute("DELETE FROM versions WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM inventorship_log WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
