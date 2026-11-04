# Using CellProfiler in a coding-agent loop

CellProfiler turns microscopy images into measurements of individual cells.
Its segmentation settings control how cells and nuclei are separated into objects.
Splitting one nucleus into several objects or joining neighboring nuclei changes what downstream modules measure.
Tuning these settings therefore requires numerical comparisons and image inspection across multiple fields.

This repository gives a coding agent a live, headless CellProfiler session for that loop.
The agent runs Python to inspect a pipeline, try segmentation settings, and request measurements and image crops.
CellProfiler executes the image analysis; the agent reads the returned evidence, chooses the next trial, and explains its recommendation to the expert.
The three-field Cell Painting demonstration below follows one such session from an oversplitting hypothesis through candidate revision, a decision, and an independent execution check.

To use the kit, give your coding agent shell access to the repository and a tool that can open PNG files.
The kit supplies the CellProfiler session; your agent harness supplies the model and the loop that chooses tool calls.
[AGENTS.md](../../AGENTS.md) describes the available commands, Python namespace, and working method.

## A live session holds the analysis state

The session keeps the loaded pipeline, images, objects, and measurements in memory between commands.
Each `./cps exec` call runs Python in the same persistent namespace, so a candidate created in one call remains available for comparison in the next.
This gives the agent a place to explore several alternatives while preserving the current pipeline settings.
The session uses the same `cellprofiler_core` calls as CellProfiler's GUI Test Mode to load a field and run its modules.

The exploration interface focuses on `IdentifyPrimaryObjects`, the module that identifies nuclei in this pipeline.
Its `try_ipo` function calls `cellprofiler_library` on the cached input image with the current settings plus explicit overrides.
The result contains a label array, object count, threshold, and settings used; the pipeline itself stays unchanged.
The agent can keep several named candidates, compare them with the committed objects, and discard an idea without restoring a file.

The following single-field example illustrates the interface after the repository's [Quickstart](../../README.md#quickstart) has started the default session.
It is a compact example, not the command transcript of the three-field run.
The agent first inspects the current settings, measurements, and outlines with `./cps settings`, `./cps measure`, and `./cps view committed`.
It can then try a threshold correction factor of 1.1 and inspect a region that changed:

```bash
./cps exec <<'PYCODE'
cand = try_ipo(threshold_correction_factor=1.1)
print(cand['count'])
PYCODE
./cps measure cand
./cps view cand --ref committed --crop 740 870 720 850
```

`measure` reports CellProfiler size, shape, and intensity features, together with overlap-based comparisons that locate splits, merges, lost objects, and gained objects relative to the committed result.
Those comparisons guide inspection: they identify changes, not segmentation errors.
`view` writes a PNG and returns its path; the coding agent must open that file with its own image-reading tool to see the illumination-corrected DNA-channel image and object outlines.
The example crop surrounds a split reported on the default field; for a new trial, the agent chooses crops from the locations reported by `measure`.
Red outlines belong only to the reference, green only to the candidate, and yellow to both.
The agent uses those images and numbers to decide whether to revise the candidate, recommend it, or leave the settings alone.

Committing a reviewed trial is a separate step, made when the expert requests it.
`commit_ipo(threshold_correction_factor=1.1)` writes the setting through CellProfiler's API and reruns the downstream object-producing modules; `undo()` restores the previous settings and reruns those modules.
Both operations leave later measurement modules stale, so current full-pipeline measurements require a rerun from `session.stale_from` with `run_from(session.stale_from, through=None)` or an independent run of the saved pipeline.
`save_as(path)` serializes the chosen pipeline without hand-editing a `.cppipe` file, and `headless_run(pipeline_path, output_dir)` executes it in a separate CellProfiler process.
Comparing that process's exported values with the session's values checks whether the saved pipeline reproduces the selected outputs.

## Comparing the same settings across three fields

The demonstration asked a Codex coding agent to investigate apparent nuclear oversplitting without merging neighboring nuclei.
The starting point, or baseline, was the output of the unchanged JUMP Cell Painting pipeline.
This scripted brief required the agent to compare each candidate across three fields, recommend shared settings or retain the baseline, and demonstrate commit, undo, saving, and independent execution.
The brief was written for the demonstration; it did not establish that the baseline contained oversplitting.

The three inputs came from plate BR00117035: A01 site 1, A01 site 2, and A02 site 1.
These already available fields were fixed before testing settings and do not represent a plate-wide sample.
A01 site 2 contains more nuclei and touching clusters than the other two fields, giving the agent a denser field alongside two sparser fields to inspect.
The [input provenance](../../fixture/three-fields/SOURCE.md) records their sources and hashes.

![Baseline nuclei in the three Cell Painting fields](recorded/views/baseline-overview.png)

The [demonstration helpers](explore.py) extended the comparison to three fields by holding three `Session` instances in the same persistent daemon.
Each instance loaded the same pipeline on a different field, and the helpers applied each proposed setting to all three.
The agent chose the trials and interpreted their saved overlays; the helpers ran CellProfiler and collected the measurements, label arrays, and images.
The helpers use the existing Python namespace; the toolkit has no production multi-field session API.

## Revising a candidate after inspecting changed objects

The first two trials changed different parts of nuclear segmentation: threshold correction and maxima suppression.
Threshold correction adjusts the threshold used to separate foreground from background.
Maxima suppression affects which nearby candidate centers remain available to separate touching objects.
The agent applied each setting across all three fields and compared it with the unchanged baseline, using measurements to locate changed objects and image crops to inspect them.
The table reports primary nuclei before downstream edge filtering.

| Shared setting | A01 site 1 | A01 site 2 | A02 site 1 |
|---|---:|---:|---:|
| Baseline | 73 | 256 | 58 |
| Threshold correction 1.1 | 74 | 251 | 58 |
| Maxima suppression 12 | 72 | 249 | 57 |
| Maxima suppression 10 | 73 | 250 | 58 |

Threshold correction 1.1 produced a mixture of splits and merges.
It caused one split in A01 site 1, and two splits, six merges, and one lost edge object in A01 site 2.
It changed boundaries in A02 site 1 while leaving its count at 58.
The counts alone could not show whether those changes helped the segmentation.

Maxima suppression 12 reduced the counts in every field, but the inspected crops showed it joining visibly distinct bright neighbors in the two sparse fields.
That observation gave the agent a reason to revise the setting instead of treating fewer objects as evidence of corrected oversplitting.
The figure pairs illumination-corrected DNA images with comparison outlines for the first trials.

![Illumination-corrected DNA and changed outlines for threshold correction 1.1 and maxima suppression 12](recorded/views/first-trials-crops.png)

The agent reduced maxima suppression from 12 to 10 after inspecting those first trials.
This revised candidate left both sparse fields' label arrays exactly unchanged and produced six merges in the dense field, A01 site 2.
The agent inspected all six locations to determine what the reduction from 256 to 250 objects represented.

![Illumination-corrected DNA and changed outlines for all six merges with maxima suppression 10](recorded/views/revised-trial-crops.png)

The six merges supported different interpretations, even within one field.
Three removed boundaries within apparently continuous nuclear shapes, while another joined bright structures separated by a dark cleft.
Two more remained ambiguous from the images.
The coordinates below refer to the original field, with positions given as (y,x).

| Locations in A01 site 2, as (y,x) | Observed change | Possible interpretation |
|---|---|---|
| (101,32), (737,687), (907,1020) | Removed boundaries within apparently continuous nuclear shapes | Corrected oversplits |
| (742,95) | Joined bright structures separated by a dark cleft | Unwanted merge |
| (87,561), (245,504) | Joined objects in a complex cluster and a bilobed structure | Unresolved; needs expert review |

The agent retained the baseline because these images did not establish a consistently beneficial shared change.
The baseline may still contain segmentation errors, and an expert may judge some merges beneficial.
The [agent journal](recorded/actor-journal.json) records the actual actions, inspected locations, code hashes, and session identity; the executed [first trials](recorded/03-first-trials.py) and [revised trial](recorded/05-revised-trial.py) show the candidate calls.

## Checking that the saved pipeline reproduces the session

The agent checked commit and undo separately from its decision to retain the baseline.
It committed threshold correction 1.1 as a controlled trial on each field, confirmed that the committed primary-object labels matched the earlier library trial, and then undid the change.
Undo restored all five object sets' label arrays and the original settings.
All three final pipelines had identical settings before the agent saved [Selected.cppipe](recorded/Selected.cppipe).
After downstream filtering, each of Nuclei, Cells, and Cytoplasm contained 66 objects in A01 site 1, 226 in A01 site 2, and 52 in A02 site 1.

Independent execution of the saved pipeline reproduced all 15 object counts and 19,608 selected measurement values exactly.
The [independent verifier](verify.py) maps fields through Plate, Well, and Site, checks object numbering, and compares 171 feature vectors.
Those vectors cover 19 features for each of Nuclei, Cells, and Cytoplasm in every field: area, solidity, eccentricity, and mean and integrated intensity on eight channels.
All 37 reported module-error columns were zero in every field.

| Check | Recorded result | Evidence |
|---|---|---|
| Commit | Matched the earlier trial's primary-object labels in all three fields | [Commit and undo record](recorded/commit-undo.json) |
| Undo | Restored all five object sets' label arrays and the original settings | [Commit and undo record](recorded/commit-undo.json) |
| Independent execution | Matched 15 counts and 19,608 selected values exactly; all 37 reported module-error columns were zero in every field | [Verification result](recorded/verification.json) |
| Fresh-session replay | Reproduced the saved pipeline, expected values, 24 label-array files, and three figures byte-for-byte | [Replay result](recorded/replay-check.json) |
| Repository tests | Passed all 36 tests, including ten verifier cases | [Test instructions](../../README.md#tests) |

Exact agreement establishes consistency with native execution for those selected outputs.
It does not establish segmentation accuracy or cover every exported feature.
The [native log](recorded/headless.log) includes the documented HDF5 export warning; the selected numeric checks passed.

The demonstration supports a concrete workflow: the agent proposed settings, used tool outputs to find and inspect changes, revised a candidate, and preserved a selected state that independent CellProfiler execution reproduced.
Its scope remains IdentifyPrimaryObjects on one pipeline and three preselected fields from one plate.
The agent's visual interpretations were not scored against expert annotations, so the recorded results establish neither a segmentation-quality improvement nor general agent reliability on other pipelines, fields, or plates.
No model was trained.

## Replaying the recorded actions

The replay repeats the recorded trials and decision without calling a model.
It provides a way to reproduce the analysis artifacts; interpreting the images and making a new recommendation remain separate steps.
Build the image using the repository's [Quickstart](../../README.md#quickstart), then run these commands from the repository root:

```bash
./scripts/fetch_demo_data.py
./cps start
```

Start with an unchanged default session and a new output directory.
The replay refuses to overwrite an existing demonstration directory.

```bash
./cps exec <<'PYCODE'
exec(open('/work/demo/three-fields/explore.py').read())
replay(session)
PYCODE
```

Inspect the PNGs in `.cps/three-field-replay/views/`.
Run the saved pipeline in a separate container process over the combined three-row CSV, compare the outputs, and stop the session:

```bash
./cprun.sh python -m cellprofiler -c -r \
  -p /work/.cps/three-field-replay/Selected.cppipe \
  -i /work/fixture/three-fields \
  -o /work/.cps/three-field-replay/headless \
  > .cps/three-field-replay/headless.log 2>&1
python3 demo/three-fields/verify.py \
  .cps/three-field-replay/expected.json \
  .cps/three-field-replay/headless \
  .cps/three-field-replay/Selected.cppipe
./cps stop
```

A successful comparison reports exact finite numeric equality and artifact hashes.
Raw images, full exported CSVs, and intermediate label arrays stay in the ignored `data/` and `.cps/` directories.
The repository contains the compact recorded evidence and reproduction scripts.

<details>
<summary>Session and audit details</summary>

The helpers select each field's process-global input/output preferences before rerunning it.
The normal `cps status` command still describes the original field.

CellProfiler 5 re-serializes the older pipeline format on save.
Identical settings therefore do not imply byte-for-byte identity with the original pipeline file.

Independent execution took 323.358 seconds; the [native job record](recorded/headless-job.json) identifies its command and runtime.
Fresh-session replay took 67.753 seconds.
The replay's expected values passed against the original independent outputs, and its byte-identical saved pipeline did not need a second headless run.
The [replay record](recorded/replay-check.json) preserves a status-serialization error and its repair; neither changed pipeline or object state.

Both demonstration daemon sessions were stopped.
The redundant replay directory was moved to trash after its hashes were retained.
Full original outputs remain in `.cps/three-field-demo/` on Spirit for audit.

</details>
