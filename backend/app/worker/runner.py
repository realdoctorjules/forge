"""Executed INSIDE the sandbox as a fresh, isolated interpreter.

Builds a parametric part (or imports a dropped STEP file), exports STEP + STL,
writes geometry metrics to result.json. Every kernel op is checkpointed to
oplog.txt (fsync'd) so the parent can attribute a native crash/timeout to a
specific operation.

Invoked as either:
  python -I runner.py --root <dir> --part <module> --params <json> --out <dir>
                      [--simulate-crash <op>]
  python -I runner.py --root <dir> --import-step <path> --out <dir>
"""
import argparse
import json
import os
import signal
import sys
import traceback
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--part", default=None)
    ap.add_argument("--params", default="{}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--import-step", dest="import_step", default=None)
    ap.add_argument("--code", default=None, help="path to AI-generated cadquery code")
    ap.add_argument("--simulate-crash", default=None)
    args = ap.parse_args()

    out = Path(args.out)
    oplog_path = out / "oplog.txt"
    result_path = out / "result.json"
    crash_after = args.simulate_crash

    def oplog(op: str) -> None:
        with open(oplog_path, "a") as f:
            f.write(op + "\n")
            f.flush()
            os.fsync(f.fileno())

    def checkpoint(op: str) -> None:
        oplog(op)
        if crash_after and op == crash_after:
            os.kill(os.getpid(), signal.SIGSEGV)

    def fail(error_type: str, error: str) -> int:
        result_path.write_text(json.dumps({
            "ok": False, "error_type": error_type, "error": error,
            "trace": traceback.format_exc(),
        }))
        return 1

    sys.path.insert(0, args.root)

    try:
        import cadquery as cq
    except Exception as e:  # noqa: BLE001
        return fail("import_cadquery", str(e))

    # --- obtain a result Workplane: STEP import, AI-generated code, or archetype
    if args.code:
        try:
            from app.worker.import_allowlist import assert_safe, AllowlistError
            code = Path(args.code).read_text()
            try:
                assert_safe(code, allow_modules={"cadquery", "cq", "math"})
            except AllowlistError as e:
                return fail("allowlist", str(e))
            checkpoint("exec_generated_code")
            import builtins as _bi
            import math as _math
            # Guarded import: only cadquery/math; everything else raises.
            _allowed_imp = {"cadquery", "cq", "math"}
            _orig_import = _bi.__import__

            def _safe_import(name, *a, **k):
                if name.split(".")[0] not in _allowed_imp:
                    raise ImportError(f"import of '{name}' is not allowed")
                return _orig_import(name, *a, **k)

            _safe_names = ("range", "len", "float", "int", "min", "max", "abs", "round",
                           "list", "dict", "tuple", "set", "frozenset", "enumerate", "zip",
                           "map", "filter", "sum", "sorted", "reversed", "bool", "str",
                           "print", "isinstance", "pow", "divmod", "ValueError",
                           "TypeError", "Exception")
            safe_builtins = {k: getattr(_bi, k) for k in _safe_names if hasattr(_bi, k)}
            safe_builtins["__import__"] = _safe_import
            g = {"__builtins__": safe_builtins, "cq": cq, "cadquery": cq, "math": _math}
            ns: dict = {}
            exec(compile(code, "<generated>", "exec"), g, ns)
            result = ns.get("result") or g.get("result")
            if result is None:
                return fail("no_result", "generated code did not define `result`")
            source = "generated"
        except Exception as e:  # noqa: BLE001
            return fail("generated_exec", str(e))
    elif args.import_step:
        try:
            checkpoint("import_step")
            result = cq.importers.importStep(args.import_step)
            source = "step_import"
        except Exception as e:  # noqa: BLE001
            return fail("step_import", str(e))
    else:
        try:
            oplog("import_part")
            import importlib
            mod = importlib.import_module(f"app.worker.parts.{args.part}")
        except Exception as e:  # noqa: BLE001
            return fail("import", str(e))
        try:
            result = mod.build(json.loads(args.params), checkpoint)
            source = args.part
        except Exception as e:  # noqa: BLE001
            return fail("build", str(e))

    # --- common: validate, export, measure
    try:
        shape = result.val()

        checkpoint("validate")
        valid = bool(shape.isValid())
        bb = shape.BoundingBox()
        vol_mm3 = float(shape.Volume())
        faces = len(shape.Faces())
        edges = len(shape.Edges())

        checkpoint("export_step")
        cq.exporters.export(result, str(out / "part.step"), exportType="STEP")

        checkpoint("export_stl")
        cq.exporters.export(result, str(out / "part.stl"), exportType="STL")

        checkpoint("export_svg")
        # Real orthographic + isometric line-art projections (OCCT HLR) for 2D
        # technical drawings and patent figures. Each guarded so a bad view can't
        # fail the build.
        _views = ({"iso": (1, -1, 1)} if os.environ.get("FORGE_LOWMEM")
                  else {"iso": (1, -1, 1), "front": (0, -1, 0),
                        "top": (0, 0, 1), "right": (1, 0, 0)})
        svg_views = []
        for _name, _dir in _views.items():
            try:
                cq.exporters.export(
                    result, str(out / f"view_{_name}.svg"), exportType="SVG",
                    opt={"projectionDir": _dir, "showAxes": False, "showHidden": False,
                         "width": 440, "height": 340, "marginLeft": 24, "marginTop": 24,
                         "strokeWidth": 0.5})
                svg_views.append(_name)
            except Exception:  # noqa: BLE001
                pass

        checkpoint("metrics")
        metrics = {
            "svg_views": svg_views,
            "valid": valid,
            "watertight": valid,
            "bbox_mm": {"x": round(bb.xlen, 3), "y": round(bb.ylen, 3), "z": round(bb.zlen, 3)},
            "volume_mm3": round(vol_mm3, 2),
            "volume_cm3": round(vol_mm3 / 1000.0, 3),
            "faces": faces,
            "edges": edges,
        }
    except Exception as e:  # noqa: BLE001
        return fail("export", str(e))

    result_path.write_text(json.dumps({
        "ok": True, "source": source,
        "metrics": metrics,
        "files": {"step": "part.step", "stl": "part.stl"},
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
