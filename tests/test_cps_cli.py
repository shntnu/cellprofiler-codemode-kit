"""Host-side CLI checks with no live session or Podman required.

Run: python3 tests/test_cps_cli.py
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("cps", str(ROOT / "cps"))
cps = importlib.util.module_from_spec(importlib.util.spec_from_loader("cps", loader))
loader.exec_module(cps)


class ClientTests(unittest.TestCase):
    def main_exits(self, argv, message):
        with patch.object(cps.sys, "argv", ["cps", *argv]), patch.object(cps.sys, "stdin", io.StringIO()):
            with self.assertRaisesRegex(SystemExit, message):
                cps.main()

    def test_missing_and_stale_socket(self):
        with tempfile.TemporaryDirectory() as d, patch.object(cps, "SOCK", Path(d) / "cps.sock"):
            for case in ("missing", "stale"):
                if case == "stale":
                    with socket.socket(socket.AF_UNIX) as s:
                        s.bind(str(cps.SOCK))
                for argv in (["status"], ["images"], ["exec"], ["view", "x"], ["measure"], ["settings"]):
                    with self.subTest(case=case, argv=argv):
                        self.main_exits(argv, "no session running")

    def test_busy_status_and_start_preserve_session(self):
        with patch.object(cps, "call", side_effect=socket.timeout), patch.object(cps.subprocess, "run") as run:
            for command in ("status", "start"):
                with self.subTest(command=command):
                    self.main_exits([command], "session is busy; leaving it running")
            run.assert_not_called()

    def test_socket_error_does_not_trigger_restart(self):
        with patch.object(cps, "call", side_effect=PermissionError), patch.object(cps.subprocess, "run") as run:
            with self.assertRaises(PermissionError):
                cps.cmd_start(None)
            run.assert_not_called()

    def test_running_container_with_no_socket_is_preserved(self):
        state = subprocess.CompletedProcess([], 0, stdout="true\n")
        with patch.object(cps, "alive", return_value=False), patch.object(cps.subprocess, "run", return_value=state) as run:
            self.main_exits(["start"], "running but its session is not ready; leaving it running")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][:2], ["podman", "inspect"])

    def test_start_waits_for_busy_session_without_force_removal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "data").mkdir()
            args = SimpleNamespace(pipeline=root / "fixture.cppipe", input=root, full=False, timeout=600)
            results = [subprocess.CompletedProcess([], 0, stdout="false\n"),  # old stopped container
                       subprocess.CompletedProcess([], 0),  # remove stopped container
                       subprocess.CompletedProcess([], 0),  # start
                       subprocess.CompletedProcess([], 0, stdout="true\n")]  # startup is busy
            with patch.object(cps, "ROOT", root), patch.object(cps, "RUNTIME", root / ".cps"), \
                    patch.object(cps, "alive", side_effect=[False, cps.BusySession(), True]), \
                    patch.object(cps.subprocess, "run", side_effect=results) as run, \
                    patch.object(cps, "call", return_value={}), patch.object(cps, "print_status"), \
                    patch.object(cps.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
                cps.cmd_start(args)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[1], ["podman", "rm", cps.NAME])
            self.assertEqual(commands[2][0], str(root / "cprun.sh"))
            self.assertEqual(len(commands), 4)

    def test_explicit_stop_still_stops_busy_session(self):
        with patch.object(cps, "alive", side_effect=cps.BusySession), \
                patch.object(cps.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            cps.cmd_stop(None)
        self.assertEqual(run.call_args.args[0], ["podman", "stop", "-t", "10", cps.NAME])

    def test_explicit_stop_handles_shutdown_timeout(self):
        with patch.object(cps, "alive", return_value=True), patch.object(cps, "call", side_effect=socket.timeout), \
                patch.object(cps.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            cps.cmd_stop(None)
        self.assertEqual(run.call_args.args[0], ["podman", "stop", "-t", "10", cps.NAME])


if __name__ == "__main__":
    unittest.main()
