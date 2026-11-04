"""Host-only regression checks for independent three-field output verification."""

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("three_field_verification", ROOT / "demo/three-fields/verify.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pipeline = self.root / "Selected.cppipe"
        self.pipeline.write_text("synthetic pipeline identity\n")
        self.expected_path = self.root / "expected.json"
        fields = {}
        self.images, self.objects = [], {obj: [] for obj in verifier.OBJECTS}
        # Native image numbers deliberately differ from expected field insertion order.
        for index, (name, metadata) in enumerate(verifier.FIELDS.items(), 1):
            image_number = {1: 3, 2: 1, 3: 2}[index]
            counts = dict.fromkeys(verifier.COUNTS, index)
            features = {feature: [100 * index + 10 * k + n for n in range(1, index + 1)]
                        for k, feature in enumerate(verifier.FEATURES)}
            fields[name] = {"metadata": dict(zip(("Plate", "Well", "Site"), metadata)),
                            "counts": counts, "objects": {obj: features for obj in verifier.OBJECTS}}
            row = dict(zip(("Metadata_Plate", "Metadata_Well", "Metadata_Site"), metadata))
            row.update(ImageNumber=image_number, ModuleError_08IdentifyPrimaryObjects=0)
            row.update({"Count_" + obj: count for obj, count in counts.items()})
            self.images.append(row)
            for obj in verifier.OBJECTS:
                for number in reversed(range(1, index + 1)):
                    row = {"ImageNumber": image_number, "ObjectNumber": number}
                    row.update({column: features[feature][number - 1] for feature, column in verifier.FEATURES.items()})
                    self.objects[obj].append(row)
        self.expected = {"fields": fields, "pipeline_sha256": verifier.sha256(self.pipeline)}
        self.write()

    def write(self):
        self.expected_path.write_text(json.dumps(self.expected))
        for name, rows in {"Image": self.images, **self.objects}.items():
            with (self.root / (name + ".csv")).open("w", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

    def verify(self):
        return verifier.verify(self.expected_path, self.root, self.pipeline)

    def test_metadata_mapping_and_reordered_objects(self):
        report = self.verify()
        self.assertTrue(report["success"])
        self.assertEqual(report["fields"]["A01_s1"]["image_number"], 3)
        self.assertEqual(report["count_comparisons"], 15)
        self.assertEqual(report["feature_vectors_compared"], 171)
        self.assertEqual(report["values_compared"], 342)

    def test_swapped_field_identity_is_rejected(self):
        for key in ("Metadata_Plate", "Metadata_Well", "Metadata_Site"):
            self.images[0][key], self.images[1][key] = self.images[1][key], self.images[0][key]
        self.write()
        with self.assertRaisesRegex(ValueError, "counts differ"):
            self.verify()

    def test_missing_field_is_rejected(self):
        self.images.pop()
        self.write()
        with self.assertRaisesRegex(ValueError, "three image rows"):
            self.verify()

    def test_changed_feature_is_rejected(self):
        self.objects["Cells"][0]["Intensity_MeanIntensity_DNA"] += 0.001
        self.write()
        with self.assertRaisesRegex(ValueError, "Cells/MeanIntensity_DNA: values differ"):
            self.verify()

    def test_changed_count_is_rejected(self):
        self.images[0]["Count_NucleiIncludingEdges"] += 1
        self.write()
        with self.assertRaisesRegex(ValueError, "counts differ"):
            self.verify()

    def test_duplicate_object_is_rejected(self):
        rows = self.objects["Nuclei"]
        rows[2]["ObjectNumber"] = rows[1]["ObjectNumber"]
        self.write()
        with self.assertRaisesRegex(ValueError, "duplicate, or invalid object rows"):
            self.verify()

    def test_nonfinite_values_are_rejected(self):
        self.objects["Cytoplasm"][0]["AreaShape_Area"] = "NaN"
        self.write()
        with self.assertRaisesRegex(ValueError, "non-finite"):
            self.verify()

    def test_missing_expected_vector_is_rejected(self):
        self.expected["fields"]["A01_s1"]["objects"]["Nuclei"].pop("Area")
        self.expected_path.write_text(json.dumps(self.expected))
        with self.assertRaisesRegex(ValueError, "19 feature vectors"):
            self.verify()

    def test_module_error_is_rejected(self):
        self.images[0]["ModuleError_08IdentifyPrimaryObjects"] = 1
        self.write()
        with self.assertRaisesRegex(ValueError, "module reported an error"):
            self.verify()

    def test_changed_pipeline_is_rejected(self):
        self.pipeline.write_text("different pipeline\n")
        with self.assertRaisesRegex(ValueError, "pipeline SHA-256 changed"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
