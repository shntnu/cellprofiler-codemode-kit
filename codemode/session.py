"""A live, headless CellProfiler 5 session: GUI Test Mode without the GUI.

Mirrors the cellprofiler_core calls in
src/frontend/cellprofiler/gui/pipelinecontroller.py (start_debugging, do_step,
debug_init_imageset) so one image set stays in memory and modules can be
re-run from any point onward.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy
import skimage.segmentation

import cellprofiler_core.preferences as prefs

prefs.set_headless()
prefs.set_awt_headless(True)

import cellprofiler_library  # noqa: E402
from cellprofiler_core.image import ImageSetList  # noqa: E402
from cellprofiler_core.measurement import Measurements  # noqa: E402
from cellprofiler_core.object import Objects, ObjectSet  # noqa: E402
from cellprofiler_core.pipeline import Pipeline  # noqa: E402
from cellprofiler_core.reader import fill_readers  # noqa: E402
from cellprofiler_core.setting.text import LabelName  # noqa: E402
from cellprofiler_core.utilities.core.modules import fill_modules  # noqa: E402
from cellprofiler_core.workspace import Workspace  # noqa: E402
from cellprofiler_library.modules import identifyprimaryobjects  # noqa: E402
from cellprofiler_library.modules._measureobjectintensity import measure_object_intensity  # noqa: E402
from cellprofiler_library.modules._measureobjectsizeshape import measureobjectsizeshape  # noqa: E402
import cellprofiler_library.opts.threshold as ThresholdOpts  # noqa: E402
from cellprofiler_library.opts.identifyprimaryobjects import LimitObjects, UnclumpMethod  # noqa: E402

fill_modules()
fill_readers(check_config=True)

# Library kwarg -> how to write it into an IdentifyPrimaryObjects module.
# Each entry returns a list of (setting, value_text) pairs.
COMMITTABLE = {
    "threshold_correction_factor": lambda m, v: [(m.threshold.threshold_correction_factor, str(v))],
    "threshold_smoothing": lambda m, v: [(m.threshold.threshold_smoothing_scale, str(v))],
    "threshold_min": lambda m, v: [(m.threshold.threshold_range, f"{v},{m.threshold.threshold_range.max}")],
    "threshold_max": lambda m, v: [(m.threshold.threshold_range, f"{m.threshold.threshold_range.min},{v}")],
    "min_size": lambda m, v: [(m.size_range, f"{int(v)},{m.size_range.max}")],
    "max_size": lambda m, v: [(m.size_range, f"{m.size_range.min},{int(v)}")],
    "exclude_size": lambda m, v: [(m.exclude_size, "Yes" if v else "No")],
    "exclude_border_objects": lambda m, v: [(m.exclude_border_objects, "Yes" if v else "No")],
    "unclump_method": lambda m, v: [(m.unclump_method, getattr(v, "value", v))],
    "watershed_method": lambda m, v: [(m.watershed_method, getattr(v, "value", v))],
    "fill_holes_method": lambda m, v: [(m.fill_holes, getattr(v, "value", v))],
    "smoothing_filter_size": lambda m, v: [(m.automatic_smoothing, "No"), (m.smoothing_filter_size, str(v))],
    "maxima_suppression_size": lambda m, v: [(m.automatic_suppression, "No"), (m.maxima_suppression_size, str(v))],
    "low_res_maxima": lambda m, v: [(m.low_res_maxima, "Yes" if v else "No")],
}


def ipo_kwargs(module, measurements=None):
    """Library kwargs equivalent to IdentifyPrimaryObjects.run for this module's settings.

    Copied from the argument mapping in
    src/frontend/cellprofiler/modules/identifyprimaryobjects.py (run).
    The parity check proves the copy is faithful.
    """
    t = module.threshold
    if t.threshold_operation == ThresholdOpts.Method.MANUAL:
        predefined = t.manual_threshold.value
    elif t.threshold_operation == ThresholdOpts.Method.MEASUREMENT:
        predefined = float(measurements.get_current_image_measurement(t.thresholding_measurement.value))
    else:
        predefined = None
    op = t.global_operation if t.threshold_scope == ThresholdOpts.Scope.GLOBAL else t.local_operation
    if op == ThresholdOpts.Method.OTSU and t.two_class_otsu == ThresholdOpts.OtsuMethod.THREE_CLASS:
        method = ThresholdOpts.Method.MULTI_OTSU
    else:
        method = op.value
    return dict(
        threshold_method=method,
        threshold_scope=t.threshold_scope.value,
        assign_middle_to_foreground=t.assign_middle_to_foreground.value,
        log_transform=t.log_transform.value,
        threshold_correction_factor=t.threshold_correction_factor.value,
        threshold_min=t.threshold_range.min,
        threshold_max=t.threshold_range.max,
        window_size=t.adaptive_window_size.value,
        threshold_smoothing=t.threshold_smoothing_scale.value,
        lower_outlier_fraction=t.lower_outlier_fraction.value,
        upper_outlier_fraction=t.upper_outlier_fraction.value,
        averaging_method=t.averaging_method.value,
        variance_method=t.variance_method.value,
        number_of_deviations=t.number_of_deviations.value,
        automatic=module.basic,
        exclude_size=module.exclude_size.value,
        min_size=module.size_range.min,
        max_size=module.size_range.max,
        exclude_border_objects=module.exclude_border_objects.value,
        unclump_method=module.unclump_method.value,
        watershed_method=module.watershed_method.value,
        fill_holes_method=module.fill_holes.value,
        smoothing_filter_size=None if module.automatic_smoothing else module.smoothing_filter_size.value,
        low_res_maxima=module.low_res_maxima.value,
        maxima_suppression_size=module.maxima_suppression_size.value,
        automatic_suppression=module.automatic_suppression.value,
        maximum_object_count=module.maximum_object_count.value if module.limit_choice != LimitObjects.NONE.value else None,
        predefined_threshold=predefined,
    )


def ipo_inert_settings(m):
    """Settings that cannot change IdentifyPrimaryObjects labels under its other current settings.

    From cellprofiler_library separate_neighboring_objects: the smoothed image only feeds Intensity
    unclumping; Shape unclumping finds maxima on a distance transform of the thresholded objects.
    """
    unclump, watershed = m.unclump_method.value, m.watershed_method.value
    if "None" in (unclump, watershed):
        why = f"declumping is off ({'unclump' if unclump == 'None' else 'watershed'} method None)"
        return {a: why for a in ("watershed_method", "automatic_smoothing", "smoothing_filter_size",
                                 "automatic_suppression", "maxima_suppression_size", "low_res_maxima")}
    out = {}
    if unclump == "Shape":
        why = "smoothing only affects Intensity unclumping; Shape uses a distance transform"
        out.update(automatic_smoothing=why, smoothing_filter_size=why)
    if m.automatic_suppression.value:
        out["maxima_suppression_size"] = "automatic suppression is on"
    if m.size_range.min <= 10:
        out["low_res_maxima"] = "only used when the minimum diameter is above 10"
    return out


def snapshot(pipeline):
    """Every module's setting value texts, keyed by module number."""
    return {m.module_num: [s.value_text for s in m.settings()] for m in pipeline.modules(False)}


def diff(before, after, pipeline):
    rows = []
    for m in pipeline.modules(False):
        a, b = before.get(m.module_num, []), after.get(m.module_num, [])
        names = [s.text for s in m.settings()]
        for i in range(max(len(a), len(b))):
            old = a[i] if i < len(a) else None
            new = b[i] if i < len(b) else None
            if old != new:
                rows.append({"module": m.module_num, "module_name": m.module_name,
                             "setting": names[i] if i < len(names) else f"#{i}", "old": old, "new": new})
    return rows


class Session:
    def __init__(self, pipeline_path, input_dir, output_dir, record_dir=None, load_through=None):
        self.started = time.time()
        self.pid = os.getpid()
        self.pipeline_path = str(pipeline_path)
        self.input_dir, self.output_dir = str(input_dir), str(output_dir)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        prefs.set_default_image_directory(self.input_dir)
        prefs.set_default_output_directory(self.output_dir)
        self.record_dir = Path(record_dir) if record_dir else None
        if self.record_dir:
            (self.record_dir / "executed").mkdir(parents=True, exist_ok=True)
        self.pipeline = Pipeline()
        self.pipeline.load(self.pipeline_path)
        self.pipeline.test_mode = True
        self.original = snapshot(self.pipeline)
        self.history = []  # stack of snapshots taken before each commit
        self.timings = {}
        self.n_exec = 0
        self.stale_from = None  # first module whose outputs predate the latest upstream change
        self.namespace = None
        self.load(load_through)

    # -- Test Mode core -------------------------------------------------

    def load(self, through=None):
        """start_debugging + debug_init_imageset, then run the modules once (see run_from for `through`)."""
        t0 = time.time()
        base = Measurements(mode="memory")
        Workspace(self.pipeline, None, base, None, base, None).refresh_image_set()
        self.measurements = Measurements(copy=base, mode="memory")
        self.object_set = ObjectSet(can_overwrite=True)
        self.image_set_list = ImageSetList(True)
        ws = Workspace(self.pipeline, None, None, None, self.measurements, self.image_set_list)
        _, self.groupings = self.pipeline.get_groupings(ws)
        key, image_numbers = self.groupings[0]
        self.pipeline.prepare_group(ws, key, image_numbers)
        self.measurements.next_image_set(image_numbers[0])
        self.group_length = len(image_numbers)
        for m in self.pipeline.modules(False):
            if m.is_input_module():
                self.step(m)
        self.run_from(1, through=through)
        self.timings["full_field_s"] = time.time() - t0
        return self.timings["full_field_s"]

    def step(self, module):
        m = self.measurements
        m.add_image_measurement("Group_Number", 1)
        m.add_image_measurement("Group_Index", 1)
        m.add_image_measurement("Group_Length", self.group_length)
        ws = Workspace(self.pipeline, module, m, self.object_set, m, self.image_set_list)
        self.pipeline.run_module(module, ws)
        m.add_measurement("Image", "ModuleError_%02d%s" % (module.module_num, module.module_name), 0)
        # Core writes per-object ImageNumber only when ObjectNumber is new, so a Test Mode re-run that
        # changes the object count leaves it at the old length. Keep it in step with ObjectNumber.
        n = m.image_set_number
        for name in self.object_set.get_object_names():
            if m.hdf5_dict.has_data(name, "ObjectNumber", n):
                k = len(m.hdf5_dict[name, "ObjectNumber", n])
                if not m.hdf5_dict.has_data(name, "ImageNumber", n) or len(m.hdf5_dict[name, "ImageNumber", n]) != k:
                    m.hdf5_dict[name, "ImageNumber", n] = [n] * k

    def object_modules(self):
        """Numbers of modules that create objects (have a LabelName setting)."""
        return [m.module_num for m in self.pipeline.modules(False)
                if m.enabled and any(isinstance(s, LabelName) for s in m.settings())]

    def run_from(self, module, through="objects"):
        """Re-run module (number, name or instance) and what follows it in pipeline order.

        through="objects" (default) stops after the last object-creating module at or after
        `module`, skipping the measurement tail; through=None runs to the end; an int stops
        after that module. Skipped modules are reported as stale until a full run covers them.
        """
        start = self.module(module).module_num
        last = max(m.module_num for m in self.pipeline.modules(False))
        if through == "objects":
            end = max([n for n in self.object_modules() if n >= start] or [start])
        else:
            end = last if through is None else self.module(through).module_num
        t0 = time.time()
        ran = []
        for m in self.pipeline.modules(False):
            if start <= m.module_num <= end and m.enabled and not m.is_input_module():
                self.step(m)
                ran.append(m.module_num)
        dt = time.time() - t0
        if end == last and (self.stale_from is None or start <= self.stale_from):
            self.stale_from = None
        elif end < last:
            self.stale_from = min(self.stale_from or end + 1, end + 1)
        key = f"run_from_{start}_{'end' if end == last else f'through_{end}'}_s"
        self.timings[key] = dt
        return {"from_module": start, "through_module": end, "modules_run": ran, "seconds": round(dt, 3),
                "stale_from": self.stale_from}

    def module(self, ref):
        if hasattr(ref, "module_num"):
            return ref
        if isinstance(ref, int):
            # modules() hides disabled modules by default, so match on module_num.
            return next(m for m in self.pipeline.modules(False) if m.module_num == ref)
        hits = [m for m in self.pipeline.modules(False) if m.module_name == ref]
        if len(hits) != 1:
            raise ValueError(f"{len(hits)} modules named {ref!r}; use a module number")
        return hits[0]

    def ipo(self, objects_name=None):
        hits = [m for m in self.pipeline.modules(False) if m.module_name == "IdentifyPrimaryObjects"
                and (objects_name is None or m.y_name.value == objects_name)]
        if len(hits) != 1:
            raise ValueError("Specify which IdentifyPrimaryObjects by its objects name")
        return hits[0]

    # -- Inspection -----------------------------------------------------

    def counts(self):
        return {name: int(self.object_set.get_objects(name).count)
                for name in self.object_set.get_object_names()}

    def image_names(self):
        return sorted(self.measurements.get_names())

    def array_names(self):
        ns = self.namespace or {}
        return sorted(k for k, v in ns.items() if isinstance(v, numpy.ndarray) or (isinstance(v, dict) and "labels" in v))

    def image(self, name):
        """Pixel data of a pipeline image, or of a namespace array, by name."""
        if not isinstance(name, str):
            return numpy.asarray(name)
        if name in self.image_names():
            return self.measurements.get_image(name).pixel_data
        if name in self.object_set.get_object_names():
            raise ValueError(f"{name!r} is an object set, not an image; pass it as an object/labels argument. "
                             f"Images: {', '.join(self.image_names())}")
        v = (self.namespace or {}).get(name)
        if isinstance(v, numpy.ndarray):
            return v
        raise ValueError(f"No image or namespace array named {name!r}. Images: {', '.join(self.image_names())}; "
                         f"arrays: {', '.join(self.array_names()) or 'none'}")

    def labels(self, name):
        """Label matrix of an object set, a namespace array, or a try_ipo result (dict with 'labels')."""
        if isinstance(name, dict) and "labels" in name:
            return name["labels"]
        if not isinstance(name, str):
            return numpy.asarray(name)
        if name == "committed":
            name = self.ipo().y_name.value
        if name in self.object_set.get_object_names():
            return self.object_set.get_objects(name).segmented
        v = (self.namespace or {}).get(name)
        if isinstance(v, dict) and "labels" in v:
            return v["labels"]
        if isinstance(v, numpy.ndarray):
            return v
        if name in self.image_names():
            raise ValueError(f"{name!r} is an image, not an object set; pass it as the image argument. "
                             f"Object sets: {', '.join(self.object_set.get_object_names())}")
        raise ValueError(f"No object set or namespace labels named {name!r}. Object sets: "
                         f"{', '.join(self.object_set.get_object_names())}; arrays: {', '.join(self.array_names()) or 'none'}")

    def settings(self, module=None):
        """One line per visible setting: number, attribute path, label, value, and commit_ipo key if any."""
        m = self.ipo() if module is None else self.module(module)
        attrs = {id(v): k for k, v in vars(m).items()}
        if hasattr(m, "threshold"):
            attrs.update({id(v): "threshold." + k for k, v in vars(m.threshold).items()})
        keys = {}
        if m.module_name == "IdentifyPrimaryObjects":
            for key, fn in COMMITTABLE.items():
                for setting, _ in fn(m, 1):
                    keys.setdefault(id(setting), []).append(key)
        inert = ipo_inert_settings(m) if m.module_name == "IdentifyPrimaryObjects" else {}
        lines = [f"Module {m.module_num} {m.module_name}"]
        for s_ in m.visible_settings():
            key = ",".join(keys.get(id(s_), []))
            attr = attrs.get(id(s_), "?")
            lines.append(f"  {attr} | {s_.text} = {s_.value_text}" + (f"  [commit_ipo: {key}]" if key else "")
                         + (f"  (no effect: {inert[attr]})" if attr in inert else ""))
        return "\n".join(lines)

    # -- IdentifyPrimaryObjects code-mode helpers -------------------------

    def try_ipo(self, objects_name=None, **overrides):
        """Call cellprofiler_library.identifyprimaryobjects on the cached input with overrides.

        Does not touch the pipeline. Returns dict(labels, count, threshold, kwargs).
        """
        module = self.ipo(objects_name)
        img = self.measurements.get_image(module.x_name.value, must_be_grayscale=True)
        kwargs = ipo_kwargs(module, self.measurements)
        unknown = set(overrides) - set(kwargs)
        if unknown:
            raise TypeError(f"Unknown identifyprimaryobjects arguments: {sorted(unknown)}")
        kwargs.update(overrides)
        out = identifyprimaryobjects(img.pixel_data, mask=img.mask, return_cp_output=True, **kwargs)
        return {"labels": out[0], "count": int(out[7]), "threshold": float(out[12]), "kwargs": kwargs}

    def commit_ipo(self, objects_name=None, through="objects", **values):
        """Write library-style values into the module settings and re-run downstream (see run_from)."""
        module = self.ipo(objects_name)
        unknown = set(values) - set(COMMITTABLE)
        if unknown:
            raise TypeError(f"Cannot commit {sorted(unknown)}; committable: {sorted(COMMITTABLE)}")
        before = snapshot(self.pipeline)
        for key, value in values.items():
            for setting, text in COMMITTABLE[key](module, value):
                setting.value_text = text
        return self.commit(before, module, through)

    def commit(self, before, from_module, through="objects"):
        """Record a settings change made since `before` and re-run from `from_module` onward."""
        after = snapshot(self.pipeline)
        changes = diff(before, after, self.pipeline)
        self.history.append(before)
        counts_before = self.counts()
        rerun = self.run_from(from_module, through)
        result = {"changes": changes, "rerun": rerun, "counts_before": counts_before, "counts_after": self.counts()}
        self.record("commit", result)
        return result

    def undo(self, through="objects"):
        if not self.history:
            raise RuntimeError("Nothing to undo")
        before = snapshot(self.pipeline)
        target = self.history.pop()
        changed = sorted(n for n in target if target[n] != before[n])
        for m in self.pipeline.modules(False):
            if m.module_num in changed:
                m.set_settings_from_values(target[m.module_num], m.variable_revision_number, m.module_name)
        counts_before = self.counts()
        rerun = self.run_from(changed[0], through) if changed else None
        result = {"changes": diff(before, target, self.pipeline), "rerun": rerun,
                  "counts_before": counts_before, "counts_after": self.counts()}
        self.record("undo", result)
        return result

    def settings_diff(self, against="original"):
        """Diff of current settings against the loaded pipeline ('original') or the last commit ('last')."""
        base = self.original if against == "original" else (self.history[-1] if self.history else self.original)
        return diff(base, snapshot(self.pipeline), self.pipeline)

    def save_as(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as fd:
            self.pipeline.dump(fd)
        self.record("save_as", {"path": str(path), "diff_vs_original": self.settings_diff()})
        return str(path)

    def headless_run(self, pipeline_path, output_dir, timeout=1800):
        """Full `cellprofiler -c -r` run of a saved pipeline in a separate process."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "cellprofiler", "-c", "-r", "-p", str(pipeline_path),
               "-i", self.input_dir, "-o", str(output_dir)]
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log = Path(output_dir) / "cellprofiler.log"
        log.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
        result = {"cmd": cmd, "returncode": proc.returncode, "seconds": round(time.time() - t0, 2),
                  "pid": None, "log": str(log), "files": sorted(str(p) for p in Path(output_dir).rglob("*") if p.is_file())}
        self.record("headless_run", result)
        return result

    # -- Light measurements ----------------------------------------------

    def measure(self, labels=None, ref=None, channels=(), objects_name=None, per_object=False):
        """CellProfiler's own size, shape and intensity features for a labels array, plus merges and splits.

        labels and ref: object-set name, namespace name, array, or try_ipo result. labels defaults to the
        committed IdentifyPrimaryObjects objects; ref defaults to labels itself when labels names an object
        set, otherwise to the committed IdentifyPrimaryObjects objects. Intensity is on the IPO input image plus `channels`.
        Uses cellprofiler_library's MeasureObjectSizeShape and MeasureObjectIntensity functions the way
        the modules call them; no pipeline module runs.
        """
        t0 = time.time()
        module = self.ipo(objects_name)
        lab = self.labels(module.y_name.value if labels is None else labels)
        img_names = [module.x_name.value] + [c for c in channels if c != module.x_name.value]
        obj = Objects()
        obj.segmented = lab
        obj.parent_image = self.measurements.get_image(img_names[0])
        n = int(obj.count)
        res = {"count": n, "objects": {}}
        if n:
            ss = measureobjectsizeshape(obj.dense, "X", calculate_advanced=False, calculate_zernikes=False,
                                        spacing=(1.0,) * obj.dimensions)
            for f in ("Area", "Solidity", "Eccentricity"):
                res["objects"][f] = numpy.asarray(ss.get_measurement("X", "AreaShape_" + f), float)
            for name in img_names:
                im = self.measurements.get_image(name, must_be_grayscale=True)
                mi = measure_object_intensity(img=im.pixel_data, image_name=name, object_name="X",
                                              image_mask=im.mask if im.has_mask else None,
                                              object_labels=obj.get_labels(), nobjects=n, image_dimensions=im.dimensions)
                for f in ("MeanIntensity", "IntegratedIntensity"):
                    res["objects"][f"{f}_{name}"] = numpy.asarray(mi.get_measurement("X", f"Intensity_{f}_{name}"), float)
        o = res["objects"]
        pct = lambda x: [round(float(v), 4) for v in numpy.percentile(x, [10, 50, 90])] if len(x) else []
        res["summary"] = {k: pct(v) for k, v in o.items()}
        objset = lambda x: isinstance(x, str) and x in self.object_set.get_object_names()
        if ref is None:  # an object set compares with itself; anything else with the committed IPO objects
            ref = labels if objset(labels) else module.y_name.value
        reference = self.labels(ref)
        res["ref"] = ref if isinstance(ref, str) else "array"
        if objset(labels) and objset(ref) and labels != ref:
            res["warning"] = f"comparing different object sets ({labels} vs {ref}); splits and merges mix compartments"
        res["vs_ref"] = compare_labels(reference, lab)
        res["seconds"] = round(time.time() - t0, 3)
        if not per_object:
            res.pop("objects")
        return res

    # -- Image view -----------------------------------------------------

    def view(self, image=None, objects=(), crop=None, path=None, colors=None, ref=None):
        """Render an image (name or array) with object outlines (names or label arrays) to PNG.

        With ref, outlines only in ref are red, only in the first objects entry green, in both yellow.
        """
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if image is None:
            image = self.ipo().x_name.value
        pixels = self.image(image)
        if pixels.ndim == 3:
            pixels = pixels.mean(axis=2)
        lo, hi = numpy.percentile(pixels, [1, 99.5])
        gray = numpy.clip((pixels - lo) / max(hi - lo, 1e-12), 0, 1)
        rgb = numpy.dstack([gray] * 3)
        palette = colors or [(1, 0.2, 0.2), (0.2, 1, 0.2), (0.3, 0.6, 1), (1, 1, 0.2), (1, 0.3, 1)]
        legend = []
        objects = [objects] if isinstance(objects, (str, numpy.ndarray, dict)) else list(objects)
        name_of = lambda obj, i: obj if isinstance(obj, str) else f"labels[{i}]"
        if ref is not None:
            if not objects:
                raise ValueError("view with ref needs a candidate in objects")
            rb = skimage.segmentation.find_boundaries(self.labels(ref), mode="inner")
            cand = self.labels(objects[0])
            cb = skimage.segmentation.find_boundaries(cand, mode="inner")
            rgb[rb & ~cb], rgb[cb & ~rb], rgb[rb & cb] = (1, 0.2, 0.2), (0.2, 1, 0.2), (1, 1, 0.2)
            legend += [f"ref {name_of(ref, 'ref')}: {int(self.labels(ref).max())} labels (red where it differs)",
                       f"{name_of(objects[0], 0)}: {int(cand.max())} labels (green where it differs)",
                       "yellow: outlines in both"]
            objects, palette = objects[1:], [(0.3, 0.6, 1), (1, 0.3, 1)]
        for i, obj in enumerate(objects):
            lab = self.labels(obj)
            rgb[skimage.segmentation.find_boundaries(lab, mode="inner")] = palette[i % len(palette)]
            legend.append(f"{name_of(obj, i)}: {int(lab.max())} labels")
        if crop:
            y0, y1, x0, x1 = crop
            rgb = rgb[y0:y1, x0:x1]
        if path is None:
            path = Path(self.output_dir) / "views" / f"view_{int(time.time() * 1000)}.png"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        plt.imsave(path, rgb)
        return {"path": str(path), "shape": list(rgb.shape[:2]), "legend": legend}

    # -- Code mode ------------------------------------------------------

    def make_namespace(self):
        import scipy
        import skimage

        return {
            "session": self, "pipeline": self.pipeline, "measurements": self.measurements,
            "object_set": self.object_set, "modules": lambda: self.pipeline.modules(False),
            "try_ipo": self.try_ipo, "commit_ipo": self.commit_ipo, "undo": self.undo,
            "settings_diff": self.settings_diff, "save_as": self.save_as, "run_from": self.run_from,
            "headless_run": self.headless_run, "view": self.view, "counts": self.counts,
            "image": self.image, "labels": self.labels, "ipo_kwargs": ipo_kwargs,
            "measure": self.measure, "settings": lambda module=None: print(self.settings(module)),
            "cellprofiler_library": cellprofiler_library, "identifyprimaryobjects": identifyprimaryobjects,
            "np": numpy, "numpy": numpy, "skimage": skimage, "scipy": scipy,
        }

    def execute(self, code):
        """Run code in the persistent namespace; return printed output (and the traceback, if any)."""
        if self.namespace is None:
            self.namespace = self.make_namespace()
        self.n_exec += 1
        buf = io.StringIO()
        t0 = time.time()
        ok = True
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                exec(compile(code, f"<exec-{self.n_exec}>", "exec"), self.namespace)
            except (Exception, SystemExit, KeyboardInterrupt):
                # Agent code must never end the session. os._exit() bypasses this and cannot be guarded.
                ok = False
                traceback.print_exc()
        out = buf.getvalue()
        if len(out) > 20000:
            out = out[:10000] + f"\n... [{len(out) - 20000} chars truncated] ...\n" + out[-10000:]
        if self.record_dir:
            (self.record_dir / "executed" / f"{self.n_exec:03d}.py").write_text(code)
        self.record("execute", {"n": self.n_exec, "ok": ok, "seconds": round(time.time() - t0, 3), "output": out})
        return {"ok": ok, "output": out}

    def status(self):
        return {
            "pid": self.pid, "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.started)),
            "uptime_s": round(time.time() - self.started, 1), "pipeline": self.pipeline_path,
            "image_number": self.measurements.image_set_number,
            "modules": [f"{m.module_num}: {m.module_name}{'' if m.enabled else ' (disabled)'}" for m in self.pipeline.modules(False)],
            "object_counts": self.counts(), "images": self.image_names(), "commits_on_undo_stack": len(self.history),
            "stale_from_module": self.stale_from,
            "settings_diff_vs_original": self.settings_diff(), "timings_s": {k: round(v, 3) for k, v in self.timings.items()},
        }

    def record(self, kind, payload):
        if self.record_dir:
            with open(self.record_dir / "session-log.jsonl", "a") as fd:
                fd.write(json.dumps({"t": time.time(), "kind": kind, **payload}, default=str) + "\n")


def api_image(path, max_side=1024):
    """JPEG bytes of a saved view, downscaled so a long conversation stays under API request limits."""
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def compare_labels(ref, new, frac=0.5):
    """Match objects by overlap. An object 'belongs' to another when at least `frac` of its pixels lie in it.

    split: a ref object containing >= 2 new objects; merge: a new object containing >= 2 ref objects;
    lost/gained: objects with no partner at all. Centroids are (y, x).
    """
    ref, new = numpy.asarray(ref), numpy.asarray(new)
    both = (ref > 0) & (new > 0)
    nr, nn = int(ref.max()), int(new.max())
    pairs, counts = numpy.unique(ref[both].astype(numpy.int64) * (nn + 1) + new[both], return_counts=True)
    r_of, n_of = pairs // (nn + 1), pairs % (nn + 1)
    area_r = numpy.bincount(ref.ravel(), minlength=nr + 1)
    area_n = numpy.bincount(new.ravel(), minlength=nn + 1)
    new_in_ref = counts >= frac * area_n[n_of]   # most of the new object lies in that ref object
    ref_in_new = counts >= frac * area_r[r_of]
    centroid = lambda L, i: tuple(int(v) for v in numpy.argwhere(L == i).mean(axis=0))
    splits = [int(r) for r in numpy.unique(r_of[new_in_ref]) if (r_of[new_in_ref] == r).sum() >= 2]
    merges = [int(n) for n in numpy.unique(n_of[ref_in_new]) if (n_of[ref_in_new] == n).sum() >= 2]
    touched_r, touched_n = set(r_of.tolist()), set(n_of.tolist())
    lost = [i for i in range(1, nr + 1) if area_r[i] and i not in touched_r]
    gained = [i for i in range(1, nn + 1) if area_n[i] and i not in touched_n]
    return {"ref_count": nr, "count": nn, "splits": len(splits), "merges": len(merges), "lost": len(lost),
            "gained": len(gained), "split_at": [centroid(ref, r) for r in splits[:10]],
            "merge_at": [centroid(new, n) for n in merges[:10]],
            "lost_at": [centroid(ref, i) for i in lost[:10]], "gained_at": [centroid(new, i) for i in gained[:10]],
            "identical": bool(numpy.array_equal(ref, new))}


def handle(session, req):
    """One request {"tool", "args"} -> response dict. Tools: execute, view, measure, settings, status, shutdown."""
    import base64

    try:
        args = req.get("args", {})
        tool = req["tool"]
        if tool == "execute":
            return session.execute(args["code"])
        if tool == "view":
            res = session.view(args.get("image"), args.get("objects", []), crop=args.get("crop"), path=args.get("path"),
                               ref=args.get("ref"))
            if args.get("inline", True):
                res["image_b64"] = base64.b64encode(api_image(res["path"])).decode()
            return {"ok": True, **res}
        if tool == "measure":
            return {"ok": True, **session.measure(args.get("labels"), args.get("ref"), args.get("channels", ()))}
        if tool == "settings":
            return {"ok": True, "output": session.settings(args.get("module"))}
        if tool == "status":
            return {"ok": True, **session.status()}
        if tool == "shutdown":
            return {"ok": True, "shutdown": True}
        return {"ok": False, "error": f"unknown tool {tool}"}
    except Exception as e:
        # Short message for expected errors; full traceback otherwise.
        short = isinstance(e, (ValueError, TypeError, KeyError, RuntimeError))
        return {"ok": False, "error": f"{type(e).__name__}: {e}" if short else traceback.format_exc()}


def serve(session, inp, out):
    """JSON-lines protocol over a stream: {"id", "tool", "args"} -> {"id", "ok", ...}."""
    for line in inp:
        req = json.loads(line)
        out.write(json.dumps({"id": req.get("id"), **handle(session, req)}, default=str) + "\n")
        out.flush()


def serve_socket(session, path):
    """Same protocol on a unix socket, one request per connection, so clients can come and go."""
    import socket

    if os.path.exists(path):
        os.unlink(path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(8)
    while True:
        conn, _ = srv.accept()
        with conn, conn.makefile("rw") as f:
            line = f.readline()
            if not line:
                continue
            req = json.loads(line)
            res = handle(session, req)
            f.write(json.dumps(res, default=str) + "\n")
            f.flush()
        if res.get("shutdown"):
            srv.close()
            os.unlink(path)
            return


def exit_now(*_):
    """End the daemon without interpreter or JVM teardown.

    A JPype SIGSEGV during JVM teardown at daemon exit was seen once (hs_err_pid*.log); nothing in the
    session needs flushing, so skip the teardown entirely.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("pipeline")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--record")
    p.add_argument("--socket", help="serve on this unix socket instead of stdin/stdout")
    p.add_argument("--full", action="store_true", help="with --socket, run every module at load (default: through the object modules)")
    a = p.parse_args()
    # Keep the protocol channel clean: everything else that prints goes to stderr.
    proto = os.fdopen(os.dup(1), "w")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    through = None if (a.full or not a.socket) else "objects"
    session = Session(a.pipeline, a.input, a.output, a.record, load_through=through)
    if a.socket:
        import signal

        signal.signal(signal.SIGTERM, exit_now)
        print(json.dumps({"ready": True, "pid": session.pid, "load_s": round(session.timings["full_field_s"], 2)}), flush=True)
        serve_socket(session, a.socket)
        exit_now()
    proto.write(json.dumps({"ready": True, "pid": session.pid, "load_s": round(session.timings["full_field_s"], 2)}) + "\n")
    proto.flush()
    serve(session, sys.stdin, proto)


if __name__ == "__main__":
    main()
