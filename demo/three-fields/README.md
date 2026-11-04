# Cell Painting segmentation tuning

The agent retained the baseline after three shared setting changes produced mixed results.
A Codex coding agent tested IdentifyPrimaryObjects settings on three public Cell Painting fields, inspected changed objects, and revised a candidate before recommending expert review.
Independent CellProfiler execution then reproduced all 15 object counts and 19,608 selected measurement values exactly.

This demonstration records one coding-agent session and provides a replay of its actions.
It shows cross-field comparison, reversible editing, and reproducible execution.
Segmentation quality remains unscored, and three fields cannot establish general agent reliability.

## Three fields shared one pipeline

The scripted task asked the agent to investigate apparent nuclear oversplitting without merging neighboring nuclei.
The agent had to compare each candidate across all three fields, recommend shared settings or retain the baseline, and demonstrate commit, undo, saving, and independent execution.
This brief was written for the demonstration.

The inputs came from plate BR00117035: A01 site 1, A01 site 2, and A02 site 1.
The fields were already available and were fixed before testing settings; they do not represent a plate-wide sample.
A01 site 2 contains more nuclei and touching clusters than the other two fields.
The [input provenance](../../fixture/three-fields/SOURCE.md) records their sources and hashes.

![Baseline nuclei in the three Cell Painting fields](recorded/views/baseline-overview.png)

## Three setting changes produced mixed results

The agent applied each candidate setting to all three fields and compared the results with the unchanged baseline.
The table reports primary nuclei before downstream edge filtering.

| Shared setting | A01 site 1 | A01 site 2 | A02 site 1 |
|---|---:|---:|---:|
| Baseline | 73 | 256 | 58 |
| Threshold correction 1.1 | 74 | 251 | 58 |
| Maxima suppression 12 | 72 | 249 | 57 |
| Maxima suppression 10 | 73 | 250 | 58 |

The agent used CellProfiler measurements and overlap-based comparisons to locate changed objects, then inspected image crops at those locations.
Split, merge, lost, and gained labels describe changes from the baseline; they do not identify segmentation errors.

**Threshold correction 1.1 split and merged objects.**

It caused one split in A01 site 1, and two splits, six merges, and one lost edge object in A01 site 2.
It changed boundaries in A02 site 1 while leaving its count at 58.

**Maxima suppression 12 merged objects in every field.**

It reduced all three counts, but image crops showed it joining visibly distinct bright neighbors in the two sparse fields.

![Corrected DNA and changed outlines for threshold correction 1.1 and maxima suppression 12](recorded/views/first-trials-crops.png)

**Maxima suppression 10 preserved the sparse fields and merged objects in the dense field.**

The agent reduced the setting from 12 to 10 after inspecting the first trials.
The revised candidate left both sparse fields' label arrays exactly unchanged and produced six merges in A01 site 2.
The agent inspected all six.

![Corrected DNA and changed outlines for all six merges with maxima suppression 10](recorded/views/revised-trial-crops.png)

The six merges supported different interpretations:

| Locations in A01 site 2, as (y,x) | Observed change | Possible interpretation |
|---|---|---|
| (101,32), (737,687), (907,1020) | Removed boundaries within apparently continuous nuclear shapes | Corrected oversplits |
| (742,95) | Joined bright structures separated by a dark cleft | Unwanted merge |
| (87,561), (245,504) | Joined objects in a complex cluster and a bilobed structure | Unresolved; needs expert review |

Red outlines belong only to the baseline, green only to the candidate, and yellow to both.
The coordinates refer to the original field.

The agent retained the baseline because these images did not establish a consistently beneficial shared change.
The baseline may still contain segmentation errors, and an expert may judge some merges beneficial.
The [agent journal](recorded/actor-journal.json) records the actual actions, inspected locations, code hashes, and session identity.

## Execution checks reproduced the selected result

The agent committed threshold correction 1.1 as a controlled trial on each field, then undid it.
All three final pipelines had identical settings before the agent saved [Selected.cppipe](recorded/Selected.cppipe).
Each of Nuclei, Cells, and Cytoplasm contained 66 objects in A01 site 1, 226 in A01 site 2, and 52 in A02 site 1.

| Check | Recorded result | Evidence |
|---|---|---|
| Commit | Matched the earlier trial's primary-object labels in all three fields | [Commit and undo record](recorded/commit-undo.json) |
| Undo | Restored all five object sets' label arrays and the original settings | [Commit and undo record](recorded/commit-undo.json) |
| Independent execution | Matched 15 counts and 19,608 selected values exactly; all 37 reported module-error columns were zero in every field | [Verification result](recorded/verification.json) |
| Fresh-session replay | Reproduced the saved pipeline, expected values, 24 label-array files, and three figures byte-for-byte | [Replay result](recorded/replay-check.json) |
| Repository tests | Passed all 36 tests, including ten verifier cases | [Test instructions](../../README.md#tests) |

The [independent verifier](verify.py) maps fields through Plate, Well, and Site, checks object numbering, and compares 171 feature vectors.
Those vectors cover 19 features for each of Nuclei, Cells, and Cytoplasm in every field: area, solidity, eccentricity, and mean and integrated intensity on eight channels.
Exact agreement establishes consistency with native execution for those selected outputs.
It does not establish segmentation accuracy or cover every exported feature.
The [native log](recorded/headless.log) includes the documented HDF5 export warning; the selected numeric checks passed.

## Replay the recorded actions

Build the image using the repository's [Quickstart](../../README.md#quickstart), then run these commands from the repository root:

```bash
./scripts/fetch_demo_data.py
./cps start
```

Start with an unchanged default session and a new output directory.
The replay refuses to overwrite an existing demonstration directory.
It repeats the recorded trials and decision without calling a model; interpreting the resulting images remains a separate step.

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

The exploration used three Session instances in one persistent CellProfiler daemon, with no new production session API.
The helpers select each field's process-global input/output preferences before rerunning it.
The normal `cps status` command still describes the original field.
No model was trained.

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

## Scope remains one pipeline and three fields

The demonstration covers IdentifyPrimaryObjects on three preselected fields from one plate.
The agent's visual interpretations were not scored against expert annotations.
The recorded results support the demonstrated actions and execution checks; they do not establish a segmentation-quality improvement or predict performance on other pipelines, fields, or plates.
