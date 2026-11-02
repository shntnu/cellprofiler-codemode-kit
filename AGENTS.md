# Working in a live CellProfiler session

You are assisting a CellProfiler expert who is tuning IdentifyPrimaryObjects on one field of a Cell Painting experiment.
A live, headless CellProfiler 5 session holds the pipeline and the field in memory.
You drive it by running Python inside it through `./cps`.
Do not edit `.cppipe` files by hand.
The expert knows CellProfiler and Cell Painting; skip explanations of the basics.

## Starting

Run `./cps status`.
If it says no session is running, run `./cps start`, which takes about 15 s.
If the image or data is missing, the README covers setup; ask the expert before building the image (about 15 minutes).
The fixture is JUMP `JUMP_analysis_v3.cppipe` on plate BR00117035, well A01, site 1.
IdentifyPrimaryObjects is module 8; it makes NucleiIncludingEdges from CorrBlue.

## Commands

| Command | What it does |
|---|---|
| `./cps status` | Session PID, object counts, image names, undo depth, first stale module, settings diff from the original |
| `./cps images` | Image names, for `-i`, `-c` and `image()` |
| `./cps settings [MODULE]` | Visible settings of a module (default IdentifyPrimaryObjects): attribute path, label, value, and the `commit_ipo` keyword that sets it |
| `./cps exec [FILE]` | Run Python from FILE or stdin in the persistent namespace; prints what the code prints |
| `./cps measure [LABELS] [--ref REF] [-c CHANNEL]` | Count; 10th, 50th and 90th percentiles of area, solidity, eccentricity, and mean and integrated intensity; splits, merges, lost and gained objects against REF, with locations as (y,x) |
| `./cps view [OBJECTS] [--ref REF] [-i IMAGE] [--crop Y0 Y1 X0 X1]` | Write an outline overlay PNG and print its path; read the PNG to look at it |

LABELS, OBJECTS and REF accept three kinds of name:
- an object set, such as `NucleiIncludingEdges`, `Nuclei` or `Cells`;
- a namespace variable holding a label array or a `try_ipo` result;
- `committed`, the IdentifyPrimaryObjects objects as they are now.

LABELS and REF default to `committed`.
In `view --ref`, red outlines are only in REF, green only in the candidate, and yellow in both.

Use a heredoc for multi-line code:

```bash
./cps exec <<'EOF'
for f in (0.9, 1.1, 1.3):
    r = try_ipo(threshold_correction_factor=f)
    print(f, r['count'], round(r['threshold'], 5))
EOF
```

## Namespace

- `try_ipo(**overrides)` calls `cellprofiler_library`'s `identifyprimaryobjects` on the cached input image, using the module's current settings plus the overrides.
  It returns `{'labels', 'count', 'threshold', 'kwargs'}` and never changes the pipeline.
  Overrides use library keyword names: `threshold_correction_factor`, `threshold_smoothing`, `threshold_min`, `threshold_max`, `min_size`, `max_size`, `exclude_size`, `exclude_border_objects`, `unclump_method`, `watershed_method`, `fill_holes_method`, `smoothing_filter_size`, `maxima_suppression_size`, `low_res_maxima`, and the other `ipo_kwargs(module)` keys.
- `measure(labels, ref, channels)` and `view(image, objects, crop, ref)` are the Python forms of the commands.
- `commit_ipo(**values)` writes values into the IdentifyPrimaryObjects settings and re-runs from module 8 through the last object module (IdentifySecondaryObjects, FilterObjects, IdentifyTertiaryObjects).
  It returns the settings changes and the counts before and after.
- `undo()` reverts the last commit and re-runs; `settings_diff()` diffs against the original pipeline.
- `save_as(path)` writes the current pipeline.
  `headless_run(pipeline_path, output_dir)` runs `cellprofiler -c -r` on a saved pipeline in a separate process, writing the pipeline's CSVs; it takes about 2 minutes.
- `run_from(module, through=None)` re-runs part of the pipeline.
  Commits skip the measurement modules (12 onward), which then stay stale; `session.stale_from` names the first stale module, and `run_from(session.stale_from, through=None)` refreshes them in about 85 s.
- `counts()`, `image(name)`, `labels(name)`, `settings()`, `modules()`, `pipeline`, `measurements` and `object_set` give direct access.
  `np`, `scipy`, `skimage` and `cellprofiler_library` are imported. pandas is not installed; use `csv`.
- Names persist between `exec` calls.
  Paths inside the session start at `/work`, which is the repo root on the host; write files under `/work/.cps/`.

## How to iterate

1. Look before changing anything: `./cps measure`, then `./cps view committed --crop ...` on the regions in question.
2. Try candidates with `try_ipo`, and store each in a named variable.
3. For each candidate, run `./cps measure NAME`, which compares against `committed` by default.
   View it with `--ref committed`, cropped to the reported split, merge, lost or gained locations.
4. Report what changed and where, with the numbers and the images you looked at.
   Recommend a setting or recommend leaving it alone; if the evidence does not support the expert's premise, say so.
5. Commit only when the expert asks, with `commit_ipo`.
   Then report counts before and after for every object set.
   If they want measurements or a saved pipeline, refresh the stale modules or use `save_as` and `headless_run`.

## Evidence

Back every claim with printed numbers or an image you viewed in this session, and say which.
Label inferences as inferences.
Counts, areas and intensities from `measure` are CellProfiler's own values: they match the full pipeline's MeasureObjectSizeShape and MeasureObjectIntensity output exactly.
Do not judge segmentation quality beyond what the images and numbers show; the expert decides what is correct.

## Limits

- Library-level exploration covers IdentifyPrimaryObjects only.
  Other modules can be inspected through `pipeline` and `settings(n)`, but commit and undo are built and tested for IdentifyPrimaryObjects settings.
- One field.
  Nothing here says how a setting behaves on other fields or plates.
- The session handles one request at a time.
- `os._exit()` ends the session.
  Do not call it.
- If the session dies, `./cps start` loads a fresh one, and uncommitted variables are lost.
  Commits are lost too unless you saved the pipeline.
