"""Focused session tests on the JUMP fixture trimmed to modules 1-11 (no measurement modules).

Run inside the container:  ./cprun.sh python -m pytest -q /work/tests
"""

import io
import json
import os

import numpy
import pytest

from codemode.session import Session, serve

PIPELINE = "/work/fixture/JUMP_analysis_v3.cppipe"
INPUT = "/work/fixture"


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    from cellprofiler_core.pipeline import Pipeline

    tmp = tmp_path_factory.mktemp("s")
    p = Pipeline()
    p.load(PIPELINE)
    for m in reversed(p.modules()):
        if m.module_num > 11:
            p.remove_module(m.module_num)
    trimmed = tmp / "trimmed.cppipe"
    with open(trimmed, "w") as fd:
        p.dump(fd)
    return Session(trimmed, INPUT, tmp / "out", tmp / "record")


def test_load_makes_all_objects(session):
    c = session.counts()
    assert set(c) >= {"NucleiIncludingEdges", "CellsIncludingEdges", "Nuclei", "Cells", "Cytoplasm"}
    assert c["Nuclei"] == c["Cells"] == c["Cytoplasm"] > 0
    assert c["NucleiIncludingEdges"] >= c["Nuclei"]


def test_library_matches_module(session):
    name = session.ipo().y_name.value
    assert numpy.array_equal(session.try_ipo()["labels"], session.labels(name))


def test_try_does_not_touch_pipeline(session):
    name = session.ipo().y_name.value
    before = session.labels(name).copy()
    r = session.try_ipo(threshold_correction_factor=1.5)
    assert not numpy.array_equal(r["labels"], before)
    assert numpy.array_equal(session.labels(name), before)
    assert session.settings_diff() == []
    with pytest.raises(TypeError):
        session.try_ipo(not_a_setting=1)


def test_commit_matches_try_then_undo_restores(session):
    name = session.ipo().y_name.value
    original = session.labels(name).copy()
    counts = session.counts()
    tried = session.try_ipo(threshold_correction_factor=1.1, maxima_suppression_size=12)
    r = session.commit_ipo(threshold_correction_factor=1.1, maxima_suppression_size=12)
    assert numpy.array_equal(session.labels(name), tried["labels"])
    assert r["rerun"]["from_module"] == session.ipo().module_num
    assert min(r["rerun"]["modules_run"]) == session.ipo().module_num
    texts = {row["setting"] for row in session.settings_diff()}
    assert any("correction factor" in t for t in texts)
    assert any("maxima" in t for t in texts)
    u = session.undo()
    assert u["rerun"]["modules_run"][0] == session.ipo().module_num  # disabled FlagImage must not shift numbering
    assert u["counts_after"] == counts
    assert numpy.array_equal(session.labels(name), original)
    assert session.settings_diff() == []
    with pytest.raises(RuntimeError):
        session.undo()


def test_save_as_round_trips(session, tmp_path):
    session.commit_ipo(threshold_correction_factor=1.2)
    path = session.save_as(tmp_path / "saved.cppipe")
    text = open(path).read()
    assert "Threshold correction factor:1.2" in text
    session.undo()


def test_execute_and_protocol(session):
    r = session.execute("x = counts()['Nuclei']\nprint(x)")
    assert r["ok"] and r["output"].strip() == str(session.counts()["Nuclei"])
    assert not session.execute("1/0")["ok"]
    session.execute("lab = try_ipo(threshold_correction_factor=1.3)['labels']")
    reqs = [{"id": 1, "tool": "status"},
            {"id": 2, "tool": "view", "args": {"objects": ["Nuclei", "lab"], "crop": [0, 200, 0, 200]}},
            {"id": 3, "tool": "execute", "args": {"code": "print(x)"}}]
    out = io.StringIO()
    serve(session, io.StringIO("".join(json.dumps(r) + "\n" for r in reqs)), out)
    res = [json.loads(line) for line in out.getvalue().splitlines()]
    assert res[0]["pid"] == session.pid and res[0]["ok"]
    assert res[1]["ok"] and res[1]["shape"] == [200, 200] and res[1]["image_b64"]
    assert res[2]["output"].strip() == str(session.counts()["Nuclei"])


def test_stop_module_marks_tail_stale(session):
    ipo = session.ipo().module_num
    r = session.run_from(ipo, through=ipo + 1)
    assert r["modules_run"] == [ipo, ipo + 1] and r["stale_from"] == ipo + 2
    assert session.status()["stale_from_module"] == ipo + 2
    assert session.run_from(ipo + 3, through=None)["stale_from"] == ipo + 2  # tail run skipped ipo+2
    assert session.run_from(ipo + 2, through=ipo + 2)["stale_from"] == ipo + 3
    assert session.run_from(ipo, through=None)["stale_from"] is None
    assert session.run_from(ipo)["through_module"] == max(session.object_modules())


def test_compare_labels_counts_splits_merges():
    from codemode.session import compare_labels

    one = numpy.zeros((20, 20), int)
    one[2:10, 2:18] = 1
    one[14:18, 14:18] = 2
    halves = numpy.zeros_like(one)
    halves[2:10, 2:10], halves[2:10, 10:18] = 1, 2
    r = compare_labels(one, halves)
    assert (r["splits"], r["merges"], r["lost"], r["gained"]) == (1, 0, 1, 0)
    r = compare_labels(halves, one)
    assert (r["splits"], r["merges"], r["lost"], r["gained"]) == (0, 1, 0, 1)
    assert compare_labels(one, one)["identical"]


def test_measure_matches_measurement_modules(session):
    """measure() equals MeasureObjectSizeShape and MeasureObjectIntensity run on the same objects."""
    from cellprofiler_core.pipeline import Pipeline
    from cellprofiler_core.workspace import Workspace

    full = Pipeline()
    full.load(PIPELINE)
    mods = {m.module_name: m for m in full.modules(False) if m.module_name in ("MeasureObjectSizeShape", "MeasureObjectIntensity")}
    m = session.measurements
    for mod in mods.values():
        mod.run(Workspace(session.pipeline, mod, m, session.object_set, m, session.image_set_list))
    r = session.measure("Nuclei", channels=["DNA", "Brightfield"], per_object=True)
    o = r["objects"]
    assert numpy.array_equal(o["Area"], m.get_current_measurement("Nuclei", "AreaShape_Area"))
    for f in ("Solidity", "Eccentricity"):
        assert numpy.array_equal(o[f], m.get_current_measurement("Nuclei", "AreaShape_" + f))
    for c in ("DNA", "Brightfield"):
        for f in ("MeanIntensity", "IntegratedIntensity"):
            assert numpy.array_equal(o[f"{f}_{c}"], m.get_current_measurement("Nuclei", f"Intensity_{f}_{c}"))
    assert r["ref"] == "Nuclei" and r["vs_ref"]["identical"]


def test_measure_finds_known_split(session):
    session.execute("cand = try_ipo(threshold_correction_factor=1.1)")
    r = session.measure("cand")
    assert r["count"] == 74 and r["vs_ref"]["splits"] == 1 and r["vs_ref"]["merges"] == 0
    assert session.measure()["vs_ref"]["identical"]
    assert r["seconds"] < 1


def test_clear_name_errors_and_settings(session):
    with pytest.raises(ValueError, match="object set, not an image"):
        session.view(image="Nuclei")
    with pytest.raises(ValueError, match="image, not an object set"):
        session.view(objects=["CorrBlue"])
    with pytest.raises(ValueError, match="Object sets: .*arrays: .*cand"):
        session.labels("nosuch")
    assert session.view(objects=["cand"], crop=[0, 50, 0, 50])["legend"] == ["cand: 74 labels"]
    text = session.settings()
    assert "threshold.threshold_correction_factor | Threshold correction factor = 1" in text
    assert "[commit_ipo: maxima_suppression_size]" in text


def test_image_number_follows_object_count(session):
    session.commit_ipo(threshold_correction_factor=1.1)
    m = session.measurements
    for name in ("NucleiIncludingEdges", "Nuclei", "Cytoplasm"):
        assert len(m.get_current_measurement(name, "ImageNumber")) == len(m.get_current_measurement(name, "ObjectNumber"))
    session.undo()


def test_socket_server_keeps_state_across_clients(session, tmp_path):
    import socket
    import threading

    from codemode.session import serve_socket

    path = str(tmp_path / "s.sock")
    t = threading.Thread(target=serve_socket, args=(session, path), daemon=True)
    t.start()
    while not os.path.exists(path):
        pass

    def call(tool, args=None):
        s = socket.socket(socket.AF_UNIX)
        s.connect(path)
        with s, s.makefile("rw") as f:
            f.write(json.dumps({"tool": tool, "args": args or {}}) + "\n")
            f.flush()
            return json.loads(f.readline())

    assert call("execute", {"code": "kept = 41"})["ok"]
    assert call("execute", {"code": "print(kept + 1)"})["output"] == "42\n"
    assert call("status")["pid"] == session.pid
    assert call("shutdown")["shutdown"]
    t.join(5)
    assert not t.is_alive() and not os.path.exists(path)


def test_agent_code_cannot_end_session(session):
    for code in ("raise SystemExit(3)", "import sys; sys.exit(0)", "raise KeyboardInterrupt"):
        r = session.execute(code)
        assert not r["ok"]
    assert session.execute("print('still here')")["output"] == "still here\n"


def test_status_lists_images_and_view_ref(session):
    assert {"DNA", "ER", "RNA", "AGP", "Mito", "CorrBlue"} <= set(session.status()["images"])
    session.execute("cand = try_ipo(threshold_correction_factor=1.1)")
    r = session.view(objects=["cand"], ref="committed", crop=[740, 870, 720, 850])
    assert r["legend"][0].startswith("ref committed: 73") and r["legend"][1].startswith("cand: 74")
    import matplotlib.pyplot as plt
    px = plt.imread(r["path"])[..., :3]
    green = (px[..., 1] > 0.9) & (px[..., 0] < 0.3)
    yellow = (px[..., 0] > 0.9) & (px[..., 1] > 0.9) & (px[..., 2] < 0.3)
    assert green.any() and yellow.any()  # the split adds a new outline; unchanged outlines are shared
    assert session.measure("cand", ref="committed")["vs_ref"]["splits"] == 1


def test_measure_ref_defaults_and_inert_settings(session):
    r = session.measure("Cells")
    assert r["ref"] == "Cells" and r["vs_ref"]["identical"] and "warning" not in r
    r = session.measure("Cells", ref="Nuclei")
    assert "different object sets" in r["warning"]
    session.execute("cand = try_ipo(threshold_correction_factor=1.1)")
    assert session.measure("cand")["ref"] == "NucleiIncludingEdges"
    text = session.settings()
    line = next(x for x in text.splitlines() if x.strip().startswith("smoothing_filter_size"))
    assert "no effect" in line  # this pipeline unclumps by Shape
    assert numpy.array_equal(session.try_ipo(smoothing_filter_size=30)["labels"], session.labels("NucleiIncludingEdges"))
    assert "maxima_suppression_size" in text and "no effect" not in next(
        x for x in text.splitlines() if x.strip().startswith("maxima_suppression_size"))


def test_invalid_commit_preserves_settings_objects_and_undo(session):
    from codemode.session import snapshot

    session.commit_ipo(threshold_correction_factor=1.1)
    try:
        before = snapshot(session.pipeline)
        history = list(session.history)
        stale = session.stale_from
        objects = {name: session.labels(name).copy() for name in session.counts()}
        with pytest.raises(ValueError):
            session.commit_ipo(threshold_correction_factor=1.2, min_size="bad")
        assert snapshot(session.pipeline) == before
        assert session.history == history
        assert session.stale_from == stale
        for name, labels in objects.items():
            assert numpy.array_equal(session.labels(name), labels)
    finally:
        session.undo()
    assert session.settings_diff() == []


def test_socket_server_survives_disconnected_client(session, tmp_path, monkeypatch):
    import socket
    import threading
    import time

    import codemode.session as implementation

    entered = threading.Event()
    release = threading.Event()
    original_handle = implementation.handle

    def blocked_handle(current, request):
        if request["tool"] == "execute":
            entered.set()
            assert release.wait(5)
        return original_handle(current, request)

    monkeypatch.setattr(implementation, "handle", blocked_handle)
    path = str(tmp_path / "disconnect.sock")
    errors = []

    def serve():
        try:
            implementation.serve_socket(session, path)
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not os.path.exists(path) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert os.path.exists(path)

    def connect():
        client = socket.socket(socket.AF_UNIX)
        client.settimeout(5)
        client.connect(path)
        return client

    try:
        with connect() as abandoned:
            abandoned.sendall(json.dumps({"tool": "execute", "args": {"code": "kept_after_disconnect = 42"}}).encode() + b"\n")
            assert entered.wait(5)
        release.set()
        with connect() as client, client.makefile("rw") as stream:
            stream.write(json.dumps({"tool": "execute", "args": {"code": "print(kept_after_disconnect)"}}) + "\n")
            stream.flush()
            response = json.loads(stream.readline())
        assert response["ok"] and response["output"] == "42\n"
    finally:
        release.set()
        if thread.is_alive():
            try:
                with connect() as client, client.makefile("rw") as stream:
                    stream.write('{"tool": "shutdown"}\n')
                    stream.flush()
                    stream.readline()
            except (OSError, ValueError):
                pass
        thread.join(5)
    assert not errors and not thread.is_alive() and not os.path.exists(path)


def test_failed_rerun_marks_outputs_stale_and_remains_undoable(session, monkeypatch):
    objects = {name: session.labels(name).copy() for name in session.counts()}
    counts = session.counts()
    history_depth = len(session.history)
    step = session.step
    failed_module = session.ipo().module_num + 1

    def fail_downstream(module):
        if module.module_num == failed_module:
            raise RuntimeError("injected downstream failure")
        step(module)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(session, "step", fail_downstream)
            with pytest.raises(RuntimeError, match="injected downstream failure"):
                session.commit_ipo(threshold_correction_factor=1.1)
        assert session.stale_from == failed_module
        assert session.status()["stale_from_module"] == failed_module
        assert len(session.history) == history_depth + 1
    finally:
        if len(session.history) > history_depth:
            session.undo()
    assert session.stale_from is None
    assert session.settings_diff() == []
    assert session.counts() == counts
    for name, labels in objects.items():
        assert numpy.array_equal(session.labels(name), labels)
