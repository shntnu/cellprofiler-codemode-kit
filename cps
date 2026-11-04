#!/usr/bin/env python3
"""cps: drive a persistent headless CellProfiler 5 session from the host.

The session runs in a detached container (see cprun.sh) and listens on .cps/cps.sock.
Each cps call is a short-lived client; the session and its state survive between calls.

  cps start [--full] [--pipeline P] [--input DIR]   load the pipeline and first field (prints status)
  cps status                                        pid, counts, settings diff, stale modules
  cps exec [FILE]                                   run Python (FILE or stdin) in the session namespace
  cps view [OBJECTS...] [--ref REF] [-i IMAGE] [--crop Y0 Y1 X0 X1] [-o PNG]
                                                    with --ref: red only in REF, green only in the first object, yellow both
  cps images                                        image names usable with -i, -c and image()
  cps measure [LABELS] [--ref REF] [-c CHANNEL ...]  light measurements, merges/splits vs REF
                                                    (REF defaults to LABELS if it is an object set, else committed)
  cps settings [MODULE]                             visible settings with attribute names; flags inert ones
  cps stop

OBJECTS, LABELS and REF are object-set names, names of arrays (or try_ipo results) in the namespace,
or `committed` for the IdentifyPrimaryObjects objects as currently committed.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".cps"
SOCK = RUNTIME / "cps.sock"
NAME = "cps-codemode"
DEFAULT_PIPELINE = "fixture/JUMP_analysis_v3.cppipe"
DEFAULT_INPUT = "fixture"


def call(tool, args=None, timeout=None):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(SOCK))
    except (FileNotFoundError, ConnectionRefusedError):
        s.close()
        raise NoSession
    with s, s.makefile("rw") as f:
        f.write(json.dumps({"tool": tool, "args": args or {}}) + "\n")
        f.flush()
        line = f.readline()
    if not line:
        sys.exit("cps: session closed the connection; see `podman logs " + NAME + "`")
    return json.loads(line)


class NoSession(Exception):
    pass


class BusySession(Exception):
    pass


def alive():
    try:
        return call("status", timeout=5).get("ok", False)
    except socket.timeout:
        raise BusySession from None
    except NoSession:
        return False


def host_path(p):
    return str(ROOT / p[len("/work/"):]) if p.startswith("/work/") else p


def container_path(p):
    p = Path(p).resolve()
    try:
        return "/work/" + str(p.relative_to(ROOT))
    except ValueError:
        sys.exit(f"cps: {p} must be inside {ROOT}")


def fail(res):
    sys.exit(res.get("error") or res.get("output") or "cps: request failed")


def print_status(r):
    diff = r["settings_diff_vs_original"]
    print(f"pid {r['pid']} started {r['started']} up {r['uptime_s']}s | {r['pipeline']}")
    print("counts: " + ", ".join(f"{k} {v}" for k, v in r["object_counts"].items()))
    print("images: " + ", ".join(r["images"]))
    print(f"undo stack {r['commits_on_undo_stack']} | stale from module {r['stale_from_module']} | load {r['timings_s'].get('full_field_s')}s")
    print(f"settings diff vs original: {len(diff)}" + "".join(
        f"\n  {d['module']} {d['module_name']}: {d['setting']}: {d['old']} -> {d['new']}" for d in diff))


def cmd_start(a):
    if alive():
        print("already running")
        return print_status(call("status", timeout=5))
    state = subprocess.run(["podman", "inspect", "-f", "{{.State.Running}}", NAME], capture_output=True, text=True)
    if state.stdout.strip() == "true":
        sys.exit(f"cps: container {NAME} is running but its session is not ready; leaving it running")
    if not (ROOT / "data").is_dir():
        sys.exit("cps: data/ is missing; run ./scripts/fetch_data.py first")
    RUNTIME.mkdir(exist_ok=True)
    # A concurrent start must fail on the name conflict, never remove a running session.
    subprocess.run(["podman", "rm", NAME], capture_output=True)
    cmd = [str(ROOT / "cprun.sh"), "python", "-m", "codemode.session", container_path(a.pipeline),
           "--input", container_path(a.input), "--output", "/work/.cps/output", "--record", "/work/.cps/record",
           "--socket", "/work/.cps/cps.sock"] + (["--full"] if a.full else [])
    t0 = time.time()
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   env={**os.environ, "CPRUN_PODMAN_ARGS": f"-d --name {NAME}"})
    while True:
        try:
            if alive():
                break
        except BusySession:
            pass
        state = subprocess.run(["podman", "inspect", "-f", "{{.State.Running}}", NAME], capture_output=True, text=True)
        if state.stdout.strip() != "true":
            logs = subprocess.run(["podman", "logs", "--tail", "30", NAME], capture_output=True, text=True)
            sys.exit("cps: session exited during start:\n" + logs.stdout + logs.stderr)
        if time.time() - t0 > a.timeout:
            sys.exit(f"cps: not ready after {a.timeout}s; see `podman logs {NAME}`")
        time.sleep(0.5)
    print(f"started in {time.time() - t0:.1f}s")
    print_status(call("status", timeout=5))


def cmd_stop(a):
    try:
        if alive():
            call("shutdown", timeout=30)
    except (NoSession, BusySession, socket.timeout):
        pass
    subprocess.run(["podman", "stop", "-t", "10", NAME], capture_output=True)
    print("stopped")


def cmd_status(a):
    if not alive():
        sys.exit("cps: no session running; `cps start`")
    print_status(call("status", timeout=5))


def cmd_exec(a):
    code = Path(a.file).read_text() if a.file and a.file != "-" else sys.stdin.read()
    r = call("execute", {"code": code})
    sys.stdout.write(r.get("output", ""))
    if not r.get("ok"):
        sys.exit(1)


def cmd_images(a):
    print(" ".join(call("status")["images"]))


def cmd_view(a):
    args = {"objects": a.objects, "image": a.image, "crop": a.crop, "ref": a.ref, "inline": False}
    if a.out:
        args["path"] = container_path(a.out)
    r = call("view", args)
    if not r.get("ok"):
        fail(r)
    print(host_path(r["path"]))
    colors = "" if a.ref else " | colors in order: red, green, blue, yellow, magenta"
    print(f"{r['shape'][0]}x{r['shape'][1]} | " + "; ".join(r["legend"]) + colors)


def cmd_measure(a):
    r = call("measure", {"labels": a.labels, "ref": a.ref, "channels": a.channel})
    if not r.get("ok"):
        fail(r)
    v = r["vs_ref"]
    print(f"{a.labels or 'committed'}: {r['count']} objects vs ref {r['ref']} {v['ref_count']} | "
          f"splits {v['splits']} merges {v['merges']} lost {v['lost']} gained {v['gained']}"
          + (" | identical" if v["identical"] else "") + f" | {r['seconds']}s")
    if r.get("warning"):
        print("  warning: " + r["warning"])
    for k in ("split_at", "merge_at", "lost_at", "gained_at"):
        if v[k]:
            print(f"  {k} (y,x): " + " ".join(f"({y},{x})" for y, x in v[k]))
    print("  p10 / p50 / p90:")
    for k, vals in r["summary"].items():
        print(f"    {k}: " + " / ".join(f"{x:.4g}" for x in vals))


def cmd_settings(a):
    r = call("settings", {"module": int(a.module) if a.module and a.module.isdigit() else a.module})
    if not r.get("ok"):
        fail(r)
    print(r["output"])


def main():
    p = argparse.ArgumentParser(prog="cps", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--full", action="store_true", help="run every module at load, not just through the object modules")
    s.add_argument("--pipeline", default=str(ROOT / DEFAULT_PIPELINE))
    s.add_argument("--input", default=str(ROOT / DEFAULT_INPUT))
    s.add_argument("--timeout", type=int, default=600)
    s.set_defaults(fn=cmd_start)
    sub.add_parser("stop").set_defaults(fn=cmd_stop)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("images").set_defaults(fn=cmd_images)
    s = sub.add_parser("exec")
    s.add_argument("file", nargs="?")
    s.set_defaults(fn=cmd_exec)
    s = sub.add_parser("view")
    s.add_argument("objects", nargs="*")
    s.add_argument("--ref")
    s.add_argument("-i", "--image")
    s.add_argument("--crop", nargs=4, type=int, metavar=("Y0", "Y1", "X0", "X1"))
    s.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_view)
    s = sub.add_parser("measure")
    s.add_argument("labels", nargs="?")
    s.add_argument("--ref")
    s.add_argument("-c", "--channel", action="append", default=[])
    s.set_defaults(fn=cmd_measure)
    s = sub.add_parser("settings")
    s.add_argument("module", nargs="?")
    s.set_defaults(fn=cmd_settings)
    a = p.parse_args()
    try:
        a.fn(a)
    except NoSession:
        sys.exit("cps: no session running; `cps start`")
    except (BusySession, socket.timeout):
        sys.exit("cps: session is busy; leaving it running. Try again when the current operation finishes.")


if __name__ == "__main__":
    main()
