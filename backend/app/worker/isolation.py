"""Isolated execution of CAD code in a separate OS process.

P0 isolation guarantees, implemented WITHOUT Docker (not installed here):
  - Separate process (fresh `python -I`), not a thread/fork in the backend.
  - macOS `sandbox-exec`: DENY all network (egress) + DENY filesystem writes
    except the per-run scratch dir. This is the honest substitute for a
    container's network/FS confinement on this machine.
  - Hard wall-clock timeout -> SIGKILL the whole process group (catches OCCT
    hangs/infinite loops that Python cannot interrupt).
  - Signal-level crash detection: a process killed by SIGSEGV/SIGABRT/SIGBUS
    exits with returncode == -signal; this is NOT catchable by try/except in
    the child, so we detect it from the parent.
  - Per-operation crash attribution via the child's fsync'd oplog.

LIMITATION (logged honestly): sandbox-exec is macOS-only and deprecated by
Apple. On a host without it we fall back to a plain subprocess with timeout +
crash detection + the AST import-allowlist, but WITHOUT kernel-enforced
network/FS confinement. The production target is a network-egress-denied,
read-only-rootfs container (a P0+ hardening, tracked in the roadmap).
"""
from __future__ import annotations

import json
import os
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]   # forge/backend
SCRATCH_ROOT = BACKEND_DIR / "scratch"
# Local dev uses the project venv; in the Docker/cloud image there is no venv,
# so fall back to the running interpreter (which has cadquery installed).
_VENV_PY = BACKEND_DIR / ".venv" / "bin" / "python"
VENV_PY = _VENV_PY if _VENV_PY.exists() else Path(sys.executable)
RUNNER = Path(__file__).resolve().parent / "runner.py"

SANDBOX_EXEC = shutil.which("sandbox-exec") if sys.platform == "darwin" else None

CRASH_SIGNALS = {
    int(signal.SIGSEGV): "SIGSEGV",
    int(signal.SIGABRT): "SIGABRT",
    int(signal.SIGBUS): "SIGBUS",
    int(signal.SIGILL): "SIGILL",
    int(signal.SIGFPE): "SIGFPE",
}

DEFAULT_TIMEOUT_S = 30.0


def _sandbox_profile(scratch: Path) -> str:
    # allow-by-default keeps the interpreter + OCCT working; the two DENY lines
    # are the teeth. Writes are confined to scratch + the OS temp areas.
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        "(deny file-write*)\n"
        f'(allow file-write* (subpath "{scratch}"))\n'
        '(allow file-write* (subpath "/private/var/folders"))\n'
        '(allow file-write* (subpath "/private/tmp"))\n'
        '(allow file-write* (subpath "/tmp"))\n'
        '(allow file-write* (literal "/dev/null"))\n'
    )


def run_part(
    part_module: str | None = None,
    params: dict | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    simulate_crash_op: str | None = None,
    import_step: str | None = None,
    generated_code: str | None = None,
) -> dict:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    scratch = SCRATCH_ROOT / run_id
    scratch.mkdir(parents=True)

    inner = [str(VENV_PY), "-I", str(RUNNER), "--root", str(BACKEND_DIR), "--out", str(scratch)]
    if generated_code is not None:
        code_path = scratch / "generated_code.py"
        code_path.write_text(generated_code)
        inner += ["--code", str(code_path)]
    elif import_step:
        inner += ["--import-step", import_step]
    else:
        inner += ["--part", part_module or "", "--params", json.dumps(params or {})]
    if simulate_crash_op:
        inner += ["--simulate-crash", simulate_crash_op]

    sandboxed = False
    if SANDBOX_EXEC:
        prof = scratch / "sandbox.sb"
        prof.write_text(_sandbox_profile(scratch))
        cmd = [SANDBOX_EXEC, "-f", str(prof)] + inner
        sandboxed = True
    else:
        cmd = inner

    # Minimal env; redirect everything that might write to disk into scratch.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "MPLCONFIGDIR": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "FORGE_LOWMEM": os.environ.get("FORGE_LOWMEM", ""),
    }

    oplog_path = scratch / "oplog.txt"
    result_path = scratch / "result.json"

    start = time.time()
    timed_out = False
    proc = subprocess.Popen(
        cmd, cwd=str(scratch), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,   # own process group so we can kill OCCT hangs
    )
    try:
        _, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        _, stderr = proc.communicate()

    elapsed = time.time() - start
    rc = proc.returncode

    last_op = None
    op_trace: list[str] = []
    if oplog_path.exists():
        op_trace = [ln.strip() for ln in oplog_path.read_text().splitlines() if ln.strip()]
        last_op = op_trace[-1] if op_trace else None

    crash = None
    if rc is not None and rc < 0:
        sig = -rc
        if timed_out or sig == int(signal.SIGKILL):
            crash = {"kind": "timeout", "signal": "SIGKILL", "timeout_s": timeout_s,
                     "attributed_op": last_op}
        elif sig in CRASH_SIGNALS:
            crash = {"kind": "native_crash", "signal": CRASH_SIGNALS[sig],
                     "attributed_op": last_op}
        else:
            crash = {"kind": "killed", "signal": sig, "attributed_op": last_op}

    payload = None
    if result_path.exists():
        try:
            payload = json.loads(result_path.read_text())
        except Exception:  # noqa: BLE001
            payload = None

    ok = bool(payload and payload.get("ok")) and crash is None and rc == 0

    return {
        "ok": ok,
        "run_id": run_id,
        "scratch": str(scratch),
        "sandboxed": sandboxed,
        "sandbox_kind": "macos-sandbox-exec" if sandboxed else "subprocess-only",
        "returncode": rc,
        "elapsed_s": round(elapsed, 3),
        "op_trace": op_trace,
        "last_op": last_op,
        "crash": crash,
        "result": payload,
        "stderr_tail": (stderr.decode(errors="replace")[-2000:] if stderr else ""),
    }


# --- warm worker (fast rebuilds for live preview) --------------------------

WARM_LOOP = Path(__file__).resolve().parent / "worker_loop.py"


class WarmError(Exception):
    """The warm worker died, hung, or its pipe broke — caller should fall back
    to the one-shot isolated runner (which gives crash attribution)."""


def _warm_profile(scratch_root: Path) -> str:
    return (
        "(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"
        f'(allow file-write* (subpath "{scratch_root}"))\n'
        '(allow file-write* (subpath "/private/var/folders"))\n'
        '(allow file-write* (subpath "/private/tmp"))\n'
        '(allow file-write* (subpath "/tmp"))\n'
        '(allow file-write* (literal "/dev/null"))\n'
    )


class WarmWorker:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.sandboxed = False

    def _alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _readline(self, timeout: float) -> str | None:
        r, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not r:
            return None
        return self.proc.stdout.readline()

    def _kill(self) -> None:
        if self.proc is not None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        self.proc = None

    def start(self) -> None:
        SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
        inner = [str(VENV_PY), "-I", str(WARM_LOOP), "--root", str(BACKEND_DIR)]
        if SANDBOX_EXEC:
            prof = SCRATCH_ROOT / "warm.sb"
            prof.write_text(_warm_profile(SCRATCH_ROOT))
            cmd = [SANDBOX_EXEC, "-f", str(prof)] + inner
            self.sandboxed = True
        else:
            cmd = inner
            self.sandboxed = False
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(SCRATCH_ROOT),
               "TMPDIR": str(SCRATCH_ROOT), "MPLCONFIGDIR": str(SCRATCH_ROOT),
               "PYTHONDONTWRITEBYTECODE": "1"}
        self.proc = subprocess.Popen(
            cmd, cwd=str(SCRATCH_ROOT), env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, start_new_session=True)
        # Wait for the OCCT import (READY), scanning past any library noise.
        deadline = time.time() + 90
        while time.time() < deadline:
            line = self._readline(deadline - time.time())
            if line is None:
                if not self._alive():
                    self._kill()
                    raise WarmError("warm worker exited during startup")
                continue
            if line.strip() == "@@READY@@":
                return
        self._kill()
        raise WarmError("warm worker startup timed out")

    def build(self, part: str, params: dict, out: Path, full: bool,
              timeout: float = 30.0) -> dict:
        with self.lock:
            if not self._alive():
                self.start()
            req = {"id": uuid.uuid4().hex[:8], "part": part, "params": params,
                   "out": str(out), "full": full}
            try:
                self.proc.stdin.write(json.dumps(req) + "\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._kill()
                raise WarmError("warm worker pipe broken")
            deadline = time.time() + timeout
            while True:
                rem = deadline - time.time()
                if rem <= 0:
                    self._kill()
                    raise WarmError("warm build timed out")
                line = self._readline(rem)
                if line is None:
                    if not self._alive():
                        self._kill()
                        raise WarmError("warm worker died mid-build")
                    continue
                line = line.strip()
                if line.startswith("@@RESP@@ "):
                    return json.loads(line[len("@@RESP@@ "):])


_warm = WarmWorker()


def warm_run(part_module: str, params: dict, *, full: bool = True,
             timeout_s: float = 30.0) -> dict:
    """Run a build through the warm worker. Returns a run_part-shaped dict.
    Raises WarmError if the worker died/hung (caller falls back to run_part)."""
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    scratch = SCRATCH_ROOT / run_id
    scratch.mkdir(parents=True)
    start = time.time()
    resp = _warm.build(part_module, params, scratch, full, timeout=timeout_s)
    ok = bool(resp.get("ok"))
    return {
        "ok": ok, "run_id": run_id, "scratch": str(scratch),
        "sandboxed": _warm.sandboxed, "warm": True, "returncode": 0,
        "elapsed_s": round(time.time() - start, 3), "op_trace": [], "last_op": None,
        "crash": None,
        "result": {"metrics": resp.get("metrics")} if ok else None,
        "stderr_tail": resp.get("error", "") if not ok else "",
    }
