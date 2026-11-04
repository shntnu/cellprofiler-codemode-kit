# Three-field demonstration inputs

The demonstration uses plate BR00117035 from `cpg0016-jump`, `source_4`, batch `2021_04_26_Batch1`.
The fields are A01 site 1, A01 site 2, and A02 site 1: two sites within one well and one site from the adjacent well.
These were previously cached public inputs, fixed before this demonstration rather than selected for a desired result.
They are not a random or representative sample of the plate, and their biological or segmentation differences must be established from the images and measurements.

## Reproduce

From the repository root:

```bash
./scripts/fetch_demo_data.py
```

This verifies the four CSV fixtures and downloads or verifies 32 files in the gitignored `data/` directory: 24 raw TIFFs and eight shared illumination arrays, 96,309,762 bytes in total.
The existing single-field fixture contributes 16 of these files; their hashes remain in `scripts/fetch_data.py`.
`manifest.json` pins the 16 additional files by size and SHA-256, along with every CSV fixture.
`cprun.sh` mounts the files read-only at `/fixture/assets`.

Use `A01_s1/`, `A01_s2/`, or `A02_s1/` as the input directory for a one-field live session.
Use this directory itself as the input directory for a headless run over all three fields.
Every input directory contains the filename expected by the unmodified JUMP pipeline, `load_data_with_illum.csv`.
The pipeline remains `fixture/JUMP_analysis_v3.cppipe`; no pipeline text was edited to create these inputs.

## Provenance and checks

The source is the [official plate LoadData CSV](https://cellpainting-gallery.s3.amazonaws.com/cpg0016-jump/source_4/workspace/load_data_csv/2021_04_26_Batch1/BR00117035/load_data_with_illum.csv), SHA-256 `56d9d92a77eb6d636b73ef23a75e2df4701c4342f0576255c8959747e2601290`.
Its data rows 0, 1, and 9 (zero-based, excluding the header) provide these fields.
All 44 column names and their order are preserved.
Only the 16 `URL_*` values per row changed, from public S3 locations to `file:///fixture/assets/<filename>`.
All 28 metadata values remain identical strings to the source CSV.
The one-field CSVs and combined CSV contain the same row values.
The asset hashes were checked against the retained public download records, and every file was rehashed after copying into `data/`.
This input check establishes identity and completeness; native decoding and pipeline behavior are checked separately by the demonstration.

CellProfiler may infer different numeric metadata types from a one-row CSV and a multi-row CSV even when their cell strings are identical.
The combined manifest also assigns different ImageNumber values from three separate one-field sessions.
Compare fields by `Metadata_Plate`, `Metadata_Well`, and `Metadata_Site`, and verify the resulting measurements and objects rather than expecting identical whole CSV files.

The image data and illumination arrays are released under CC0 1.0 Universal by the [Cell Painting Gallery](https://github.com/broadinstitute/cellpainting-gallery). The JUMP pipeline's separate source and terms are recorded in [the parent provenance file](../SOURCE.md).
