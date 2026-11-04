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


def initialize(first, output_dir="/work/.cps/three-field-demo"):
    global OUT
    OUT = Path(output_dir)
    if first.history or first.settings_diff():
        raise RuntimeError("The demonstration needs an unchanged session with an empty undo history")
    source_hash = hashlib.sha256(Path(first.pipeline_path).read_bytes()).hexdigest()
    if source_hash != "1f11201c7a46dcc730fcbb9f8a72e25337505de8151edc4d16bca3a88c4a8509":
        raise RuntimeError("The demonstration needs the original JUMP fixture pipeline")
    well = str(first.measurements.get_current_image_measurement("Metadata_Well"))
    site = str(first.measurements.get_current_image_measurement("Metadata_Site"))
    if (well, site) != ("A01", "1"):
        raise RuntimeError("The initial session must contain A01 site 1")
    OUT.mkdir(parents=True, exist_ok=False)
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


def finish(fields, baselines, selected_settings, reason):
    """Replay the controlled commit/undo check, then save the explicitly selected state."""
    selected = OUT / "Selected.cppipe"
    if selected.exists() or (OUT / "expected.json").exists():
        raise FileExistsError("Final demonstration outputs already exist")
    if any(current.history or current.settings_diff() for current in fields.values()):
        raise RuntimeError("Finish expects the unchanged baseline in every field")
    audit = {"pid": fields["A01_s1"].pid, "fields": {}}
    for field, current in fields.items():
        select(current)
        trial = current.try_ipo(threshold_correction_factor=1.1)
        committed = current.commit_ipo(threshold_correction_factor=1.1)
        assert np.array_equal(current.labels("NucleiIncludingEdges"), trial["labels"])
        undone = current.undo()
        assert current.settings_diff() == []
        assert all(np.array_equal(current.labels(obj), labels) for obj, labels in baselines[field].items())
        audit["fields"][field] = {"commit": committed, "undo": undone,
                                  "library_commit_labels_equal": True,
                                  "undo_restores_all_object_labels": True}
        if selected_settings:
            trial = current.try_ipo(**selected_settings)
            current.commit_ipo(**selected_settings)
            assert np.array_equal(current.labels("NucleiIncludingEdges"), trial["labels"])
    write_json("commit-undo.json", audit)
    snapshots = [snapshot(current.pipeline) for current in fields.values()]
    assert all(value == snapshots[0] for value in snapshots[1:])
    fields["A01_s1"].save_as(selected)
    expected = {"fields": {}, "selected_settings": selected_settings,
                "pipeline_sha256": hashlib.sha256(selected.read_bytes()).hexdigest(),
                "pid": fields["A01_s1"].pid}
    feature_names = ["Area", "Solidity", "Eccentricity"] + [
        metric + "_" + channel for channel in CHANNELS for metric in ("MeanIntensity", "IntegratedIntensity")]
    for field, current in fields.items():
        select(current)
        well, site = field.split("_s")
        objects = {}
        for name in ("Nuclei", "Cells", "Cytoplasm"):
            measured = current.measure(name, channels=CHANNELS, per_object=True)["objects"]
            objects[name] = {}
            for feature in feature_names:
                values = measured[feature]
                if not np.isfinite(values).all():
                    raise ValueError("Nonfinite values in " + field + "/" + name + "/" + feature)
                objects[name][feature] = values.tolist()
        expected["fields"][field] = {"metadata": {"Plate": "BR00117035", "Well": well, "Site": site},
                                     "counts": current.counts(), "objects": objects}
    write_json("expected.json", expected)
    write_json("selection.json", {"selected_settings": selected_settings, "reason": reason,
                                  "all_field_settings_equal": True,
                                  "started": fields["A01_s1"].status()["started"],
                                  "pid": fields["A01_s1"].pid,
                                  "pipeline_sha256": expected["pipeline_sha256"]})
    print(json.dumps({"saved": str(selected), "expected": str(OUT / "expected.json"),
                      "counts": {name: value["counts"] for name, value in expected["fields"].items()},
                      "pid": expected["pid"], "pipeline_sha256": expected["pipeline_sha256"]}, indent=2))


def figures(fields, baselines, trials):
    """Recreate the inspected evidence figures; locations are the recorded demo decisions."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.3))
    for ax, field in zip(axes, FIELDS):
        ax.imshow(plt.imread(OUT / "views" / (field + "-baseline.png")))
        ax.set_title(field + ": " + str(int(baselines[field]["NucleiIncludingEdges"].max())) + " primary nuclei")
        ax.axis("off")
    fig.suptitle("Baseline: corrected DNA with IdentifyPrimaryObjects outlines")
    fig.tight_layout()
    fig.savefig(OUT / "views" / "baseline-overview.png", dpi=150)
    plt.close(fig)

    def pair(axes, field, candidate, kind, y, x):
        crop = [max(0, y - 70), min(1080, y + 70), max(0, x - 70), min(1080, x + 70)]
        prefix = field + "-" + candidate + "-" + str(y) + "-" + str(x)
        raw = fields[field].view(objects=[], crop=crop, path=OUT / "views" / (prefix + "-dna.png"))
        overlay = fields[field].view(objects=[trials[candidate][field]], ref=baselines[field]["NucleiIncludingEdges"],
                                     crop=crop, path=OUT / "views" / (prefix + "-comparison.png"))
        for ax, view in zip(axes, (raw, overlay)):
            ax.imshow(plt.imread(view["path"]))
            ax.axis("off")
        axes[0].set_title(field + " " + candidate + " " + kind + " (y,x)=" + str((y, x)), fontsize=9)
        axes[1].set_title("baseline red; candidate green; shared yellow", fontsize=8)

    examples = [("A01_s1", "tc11", "split", 804, 783), ("A01_s2", "tc11", "split", 713, 136),
                ("A01_s2", "tc11", "merge", 126, 804), ("A01_s1", "supp12", "merge", 242, 257),
                ("A01_s2", "supp12", "merge", 247, 195), ("A02_s1", "supp12", "merge", 351, 945)]
    fig, axes = plt.subplots(6, 2, figsize=(7, 17))
    for row, example in enumerate(examples):
        pair(axes[row], *example)
    fig.suptitle("Changed objects: corrected DNA (left), candidate vs baseline (right)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT / "views" / "first-trials-crops.png", dpi=130)
    plt.close(fig)

    locations = json.loads((OUT / "supp10.json").read_text())["fields"]["A01_s2"]["measurement"]["vs_ref"]["merge_at"]
    assert len(locations) == 6, "The recorded demo expected six merges; inspect changed results before interpreting them"
    fig, axes = plt.subplots(3, 4, figsize=(12, 9))
    for i, (y, x) in enumerate(locations):
        pair(axes[i // 2, 2 * (i % 2):2 * (i % 2) + 2], "A01_s2", "supp10", "merge", y, x)
    fig.suptitle("Milder suppression 10: all six reported merges in dense field A01_s2", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "views" / "revised-trial-crops.png", dpi=150)
    plt.close(fig)
