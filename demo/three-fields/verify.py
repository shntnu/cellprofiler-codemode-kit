#!/usr/bin/env python3
"""Compare the three live fields with a separate saved-pipeline headless run."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

FIELDS = {
    "A01_s1": ("BR00117035", "A01", "1"),
    "A01_s2": ("BR00117035", "A01", "2"),
    "A02_s1": ("BR00117035", "A02", "1"),
}
OBJECTS = ("Nuclei", "Cells", "Cytoplasm")
COUNTS = (*OBJECTS, "NucleiIncludingEdges", "CellsIncludingEdges")
CHANNELS = ("DNA", "RNA", "AGP", "Mito", "ER", "Brightfield", "BFHigh", "BFLow")
FEATURES = {name: "AreaShape_" + name for name in ("Area", "Solidity", "Eccentricity")}
FEATURES.update({kind + "_" + channel: "Intensity_" + kind + "_" + channel
                 for kind in ("MeanIntensity", "IntegratedIntensity") for channel in CHANNELS})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value, where):
    require(not isinstance(value, bool), f"{where}: boolean is not a measurement")
    result = float(value)
    require(math.isfinite(result), f"{where}: non-finite measurement")
    return result


def integer(value, where):
    result = number(value, where)
    require(result.is_integer(), f"{where}: expected an integer")
    return int(result)


def table(path, required):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        require(len(headers) == len(set(headers)), f"{path.name}: duplicate columns")
        require(set(required) <= set(headers), f"{path.name}: missing required columns")
        rows = list(reader)
        require(all(None not in row and None not in row.values() for row in rows),
                f"{path.name}: malformed row")
    return headers, rows


def verify(expected_path, output_dir, pipeline_path):
    expected_path, output_dir, pipeline_path = map(Path, (expected_path, output_dir, pipeline_path))
    expected = json.loads(expected_path.read_text())
    fields = expected["fields"]
    require(set(fields) == set(FIELDS), "Expected data must contain exactly the three demo fields")
    require(sha256(pipeline_path) == expected["pipeline_sha256"], "Selected pipeline SHA-256 changed")
    for name, field in fields.items():
        require(tuple(field["metadata"][key] for key in ("Plate", "Well", "Site")) == FIELDS[name],
                f"{name}: unexpected metadata")
        require(set(field["counts"]) == set(COUNTS), f"{name}: expected all five object counts")
        require(set(field["objects"]) == set(OBJECTS), f"{name}: expected all three measured object sets")
        for obj, count in field["counts"].items():
            require(type(count) is int and count >= 0, f"{name}/{obj}: invalid expected count")
        for obj, features in field["objects"].items():
            require(set(features) == set(FEATURES), f"{name}/{obj}: expected exactly 19 feature vectors")
            for feature, values in features.items():
                require(isinstance(values, list) and len(values) == field["counts"][obj],
                        f"{name}/{obj}/{feature}: expected vector length differs from count")
                for value in values:
                    require(type(value) in (int, float), f"{name}/{obj}/{feature}: expected numeric values")
                    number(value, f"{name}/{obj}/{feature}")

    image_path = output_dir / "Image.csv"
    headers, images = table(image_path, ["ImageNumber", "Metadata_Plate", "Metadata_Well", "Metadata_Site",
                                        *("Count_" + obj for obj in COUNTS)])
    error_columns = [column for column in headers if column.startswith("ModuleError_")]
    require(error_columns, "Image.csv: no module-error columns")
    require(len(images) == len(fields), "Image.csv: expected exactly three image rows")
    identity_to_name = {identity: name for name, identity in FIELDS.items()}
    image_to_name, field_report = {}, {}
    for row in images:
        identity = (row["Metadata_Plate"], row["Metadata_Well"], str(integer(row["Metadata_Site"], "Metadata_Site")))
        require(identity in identity_to_name, f"Image.csv: unexpected field {identity}")
        name = identity_to_name[identity]
        image_number = integer(row["ImageNumber"], f"{name}/ImageNumber")
        require(image_number > 0 and image_number not in image_to_name, "Image.csv: invalid or repeated ImageNumber")
        require(name not in field_report, f"Image.csv: repeated field {name}")
        counts = {obj: integer(row["Count_" + obj], f"{name}/Count_{obj}") for obj in COUNTS}
        require(counts == fields[name]["counts"], f"{name}: object counts differ")
        for column in error_columns:
            require(number(row[column], f"{name}/{column}") == 0, f"{name}/{column}: module reported an error")
        image_to_name[image_number] = name
        field_report[name] = {"image_number": image_number, "counts": counts}
    require(set(field_report) == set(fields), "Image.csv: missing field")

    vector_count = value_count = 0
    hashes = {"expected.json": sha256(expected_path), "Selected.cppipe": sha256(pipeline_path),
              "Image.csv": sha256(image_path)}
    for obj in OBJECTS:
        path = output_dir / (obj + ".csv")
        _, rows = table(path, ["ImageNumber", "ObjectNumber", *FEATURES.values()])
        grouped = {image_number: [] for image_number in image_to_name}
        for row in rows:
            image_number = integer(row["ImageNumber"], f"{obj}/ImageNumber")
            require(image_number in grouped, f"{obj}.csv: unexpected ImageNumber {image_number}")
            grouped[image_number].append(row)
        for image_number, name in image_to_name.items():
            ordered = sorted(grouped[image_number], key=lambda row: integer(row["ObjectNumber"], f"{obj}/ObjectNumber"))
            count = fields[name]["counts"][obj]
            numbers = [integer(row["ObjectNumber"], f"{name}/{obj}/ObjectNumber") for row in ordered]
            require(numbers == list(range(1, count + 1)), f"{name}/{obj}: missing, duplicate, or invalid object rows")
            for feature, column in FEATURES.items():
                actual = [number(row[column], f"{name}/{obj}/{feature}") for row in ordered]
                wanted = fields[name]["objects"][obj][feature]
                differences = [abs(a - b) for a, b in zip(actual, wanted)]
                maximum = max(differences, default=0.0)
                require(actual == wanted, f"{name}/{obj}/{feature}: values differ; max_abs_difference={maximum:.17g}")
                vector_count += 1
                value_count += len(actual)
        hashes[path.name] = sha256(path)
    return {"success": True, "comparison": "exact finite numeric equality", "fields": field_report,
            "count_comparisons": len(fields) * len(COUNTS), "feature_vectors_compared": vector_count,
            "values_compared": value_count, "max_abs_difference": 0.0,
            "module_error_columns_checked": len(error_columns), "sha256": hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("selected_pipeline", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.expected_json, args.output_dir, args.selected_pipeline)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"verification failed: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
