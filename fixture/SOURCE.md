# Fixture sources

## Pipeline

`JUMP_analysis_v3.cppipe` is the JUMP Cell Painting production analysis pipeline, unchanged (sha256 `1f11201c7a46dcc730fcbb9f8a72e25337505de8151edc4d16bca3a88c4a8509`).

- Source: https://github.com/broadinstitute/imaging-platform-pipelines/blob/7b107db5b54cbe3f0cce4e6488dc24e374d235a0/JUMP_production/JUMP_analysis_v3.cppipe
- License: that repository has no license file, so its redistribution terms are unstated.
  It is included here with attribution, for reproducibility; check with the Broad Institute Imaging Platform before reusing it elsewhere.

CellProfiler 5 upgrades the pipeline when it loads it, so a pipeline saved by the session differs from this file in module revision numbers, new settings at their defaults, and two removed display-only settings.
Loading and re-saving it without edits gives identical results on this field.

## Images

`load_data_with_illum.csv` is the first row (plate BR00117035, well A01, site 1) of the official LoadData CSV for that plate, with all 44 columns unchanged except that the 16 `URL_*` values point to `file:///fixture/assets/<file name>` instead of S3.
`cprun.sh` mounts `data/` at `/fixture/assets`.

- Original CSV: https://cellpainting-gallery.s3.amazonaws.com/cpg0016-jump/source_4/workspace/load_data_csv/2021_04_26_Batch1/BR00117035/load_data_with_illum.csv (sha256 `56d9d92a77eb6d636b73ef23a75e2df4701c4342f0576255c8959747e2601290`)
- Images and illumination files: `cpg0016-jump`, `source_4`, batch `2021_04_26_Batch1`, from the Cell Painting Gallery.
  `scripts/fetch_data.py` lists each file with its size and sha256.
- License: the Cell Painting Gallery releases its data under CC0 1.0 Universal (https://github.com/broadinstitute/cellpainting-gallery).
