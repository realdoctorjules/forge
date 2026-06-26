"""Warm persistent CAD worker — keeps cadquery/OCCT loaded for fast rebuilds.

Runs inside the same sandbox as the one-shot runner (network denied, writes
jailed to the scratch tree). Reads one JSON request per line on stdin and writes
one '@@RESP@@ <json>' line per response. Stays alive across requests; only a
native crash (segfault) kills it — the backend detects that and respawns + falls
back to the one-shot isolated runner so crash attribution is preserved.

Protocol:
  stdout "@@READY@@"                  once, after OCCT import
  in:  {"id","part","params","out","full"}
  out: "@@RESP@@ {"id","ok","metrics"|"error"}"
"""
import importlib
import json
import os
import sys


def _metrics(cq, result, out: str, full: bool) -> dict:
    shape = result.val()
    bb = shape.BoundingBox()
    vol = float(shape.Volume())
    os.makedirs(out, exist_ok=True)
    cq.exporters.export(result, os.path.join(out, "part.stl"), exportType="STL")
    m = {
        "valid": bool(shape.isValid()), "watertight": bool(shape.isValid()),
        "bbox_mm": {"x": round(bb.xlen, 3), "y": round(bb.ylen, 3), "z": round(bb.zlen, 3)},
        "volume_mm3": round(vol, 2), "volume_cm3": round(vol / 1000.0, 3),
        "faces": len(shape.Faces()), "edges": len(shape.Edges()),
    }
    if full:
        cq.exporters.export(result, os.path.join(out, "part.step"), exportType="STEP")
        views = {"iso": (1, -1, 1), "front": (0, -1, 0), "top": (0, 0, 1), "right": (1, 0, 0)}
        sv = []
        for n, d in views.items():
            try:
                cq.exporters.export(
                    result, os.path.join(out, f"view_{n}.svg"), exportType="SVG",
                    opt={"projectionDir": d, "showAxes": False, "showHidden": False,
                         "width": 440, "height": 340, "marginLeft": 24, "marginTop": 24,
                         "strokeWidth": 0.5})
                sv.append(n)
            except Exception:  # noqa: BLE001
                pass
        m["svg_views"] = sv
    return m


def _emit(obj: dict) -> None:
    sys.stdout.write("@@RESP@@ " + json.dumps(obj) + "\n")
    sys.stdout.flush()


def main() -> None:
    root = sys.argv[sys.argv.index("--root") + 1]
    sys.path.insert(0, root)
    import cadquery as cq  # warm import, paid once

    sys.stdout.write("@@READY@@\n")
    sys.stdout.flush()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            mod = importlib.import_module(f"app.worker.parts.{req['part']}")
            result = mod.build(req["params"], lambda op: None)
            _emit({"id": rid, "ok": True, "metrics": _metrics(cq, result, req["out"], req.get("full", False))})
        except Exception as e:  # noqa: BLE001 — build error, stay alive
            _emit({"id": rid, "ok": False, "error": str(e), "error_type": "build"})


if __name__ == "__main__":
    main()
