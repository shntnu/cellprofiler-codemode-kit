"""Small, replayable steps for the three-field live-session demonstration.

Load this file with cps exec, then call initialize(session), try_candidate(...),
and finish(...) as shown in the demonstration walkthrough.
The coding agent chooses the trials and interprets the saved overlays.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import cellprofiler
import cellprofiler_core.preferences as prefs
from codemode.session import Session, snapshot

OUT = Path("/work/.cps/three-field-demo")
FIELDS = ("A01_s1", "A01_s2", "A02_s1")
CHANNELS = ("DNA", "RNA", "AGP", "Mito", "ER", "Brightfield", "BFHigh", "BFLow")


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def select(current):
    # CellProfiler directory preferences are global even with separate Session objects.
    prefs.set_default_image_directory(current.input_dir)
    prefs.set_default_output_directory(current.output_dir)


def initialize(first):
    OUT.mkdir(parents=True, exist_ok=True)
    fields = {"A01_s1": first}
    for name in FIELDS[1:]:
        fields[name] = Session(
            "/work/fixture/JUMP_analysis_v3.cppipe",
            "/work/fixture/three-fields/" + name,
            OUT / name / "output", OUT / name / "record", load_through="objects")
    baselines = {}
    summary = {"pid": first.pid, "started": first.status()["started"],
               "cellprofiler_version": cellprofiler.__version__, "fields": {}}
    for name, current in fields.items():
        baselines[name] = {obj: current.labels(obj).copy() for obj in current.counts()}
        assert np.array_equal(current.try_ipo()["labels"], baselines[name]["NucleiIncludingEdges"])
        stats = current.measure("NucleiIncludingEdges")
        view = current.view(objects="NucleiIncludingEdges", path=OUT / "views" / (name + "-baseline.png"))
        summary["fields"][name] = {"counts": current.counts(), "measurement": stats, "view": view,
                                   "library_module_labels_equal": True}
        for obj, labels in baselines[name].items():
            target = OUT / "labels" / name
            target.mkdir(parents=True, exist_ok=True)
            np.save(target / (obj + "-baseline.npy"), labels)
    write_json("baseline.json", summary)
    print(json.dumps(summary, indent=2))
    return fields, baselines


def try_candidate(fields, baselines, name, changes):
    results, summary = {}, {"name": name, "changes": changes, "fields": {}}
    for field, current in fields.items():
        result = current.try_ipo(**changes)
        results[field] = result
        ref = baselines[field]["NucleiIncludingEdges"]
        stats = current.measure(result, ref=ref)
        views = [current.view(objects=[result], ref=ref,
                              path=OUT / "views" / (field + "-" + name + ".png"))]
        for kind in ("split_at", "merge_at", "lost_at", "gained_at"):
            for index, (y, x) in enumerate(stats["vs_ref"][kind][:2]):
                crop = [max(0, y - 90), min(ref.shape[0], y + 90),
                        max(0, x - 90), min(ref.shape[1], x + 90)]
                views.append(current.view(objects=[result], ref=ref, crop=crop,
                    path=OUT / "views" / (field + "-" + name + "-" + kind + str(index) + ".png")))
        summary["fields"][field] = {"count": result["count"], "threshold": result["threshold"],
                                    "measurement": stats, "views": views}
        np.save(OUT / "labels" / field / (name + ".npy"), result["labels"])
    write_json(name + ".json", summary)
    print(json.dumps(summary, indent=2))
    return results
