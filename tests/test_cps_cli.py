"""Host-side check that cps reports a missing session cleanly. Run: python3 tests/test_cps_cli.py"""
import importlib.machinery
import importlib.util
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("cps", str(ROOT / "cps"))
cps = importlib.util.module_from_spec(importlib.util.spec_from_loader("cps", loader))
loader.exec_module(cps)

with tempfile.TemporaryDirectory() as d:
    for case in ("missing", "stale"):
        cps.SOCK = Path(d) / "cps.sock"
        if case == "stale":  # a socket file left behind by a dead daemon
            s = socket.socket(socket.AF_UNIX)
            s.bind(str(cps.SOCK))
            s.close()
        for argv in (["status"], ["images"], ["exec"], ["view", "x"], ["measure"], ["settings"]):
            sys.argv = ["cps", *argv]
            sys.stdin = open("/dev/null")
            try:
                cps.main()
                raise AssertionError(f"{argv} should exit")
            except SystemExit as e:
                assert "no session running" in str(e.code), (case, argv, e.code)
if subprocess.run(["podman", "container", "exists", cps.NAME]).returncode != 0:
    out = subprocess.run([str(ROOT / "cps"), "status"], capture_output=True, text=True)
    assert out.returncode == 1 and "no session running" in out.stderr and "Traceback" not in out.stderr, out
print("ok")
