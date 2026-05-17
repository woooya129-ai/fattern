import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.orchestration import (
    build_clarification_request,
    normalize_user_intent,
    validate_clarification_request,
    validate_user_intent,
)


class UserIntentNormalizationTests(unittest.TestCase):
    def test_complete_input_matches_user_intent_schema(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "file_uploaded",
                "unit": "cm",
                "fabric_width": 150,
                "rules": {
                    "seam_allowance_included": True,
                    "one_way_fabric": False,
                    "rotation_allowed_degrees": [0, 180],
                },
            }
        )

        validate_user_intent(intent)
        self.assertEqual(intent["schema_version"], "1.0")
        self.assertEqual(intent["intent"], "estimate_yield")
        self.assertEqual(intent["unit"], "cm")
        self.assertEqual(intent["dxf_unit_hint"], "auto")
        self.assertEqual(intent["fabric"], {"width": 150, "width_unit": "cm"})
        self.assertIsNone(intent["rules"]["seam_allowance_width"])
        self.assertEqual(intent["missing_fields"], [])

    def test_default_seam_allowance_matches_unit(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "file_uploaded",
                "unit": "mm",
                "fabric_width": 1500,
                "rules": {"seam_allowance_included": False, "one_way_fabric": False},
            }
        )

        self.assertEqual(intent["rules"]["seam_allowance_width"], 10.0)

    def test_missing_file_id_maps_to_dxf_file_missing_field(self) -> None:
        intent = normalize_user_intent(
            {
                "unit": "cm",
                "fabric_width": 150,
                "rules": {"seam_allowance_included": True, "one_way_fabric": False},
            }
        )

        self.assertIn("dxf_file", intent["missing_fields"])
        self.assertNotIn("file_id", intent)

    def test_path_like_file_id_is_not_accepted_as_dxf_file(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "../outside.dxf",
                "unit": "cm",
                "fabric_width": 150,
                "rules": {"seam_allowance_included": True, "one_way_fabric": False},
            }
        )

        self.assertIn("dxf_file", intent["missing_fields"])
        self.assertNotIn("file_id", intent)

    def test_non_file_opaque_id_is_not_accepted_as_dxf_file(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "layout_marker_1",
                "unit": "cm",
                "fabric_width": 150,
                "rules": {"seam_allowance_included": True, "one_way_fabric": False},
            }
        )

        self.assertIn("dxf_file", intent["missing_fields"])
        self.assertNotIn("file_id", intent)

    def test_missing_fabric_width_is_reported(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "file_uploaded",
                "unit": "cm",
                "rules": {"seam_allowance_included": True, "one_way_fabric": False},
            }
        )

        self.assertIsNone(intent["fabric"]["width"])
        self.assertIn("fabric_width", intent["missing_fields"])

    def test_missing_unit_is_reported_without_applying_schema_default(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "file_uploaded",
                "fabric_width": 150,
                "rules": {"seam_allowance_included": True, "one_way_fabric": False},
            }
        )

        self.assertIsNone(intent["unit"])
        self.assertIn("unit", intent["missing_fields"])

    def test_unknown_one_way_fabric_is_reported(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "file_uploaded",
                "unit": "cm",
                "fabric_width": 150,
                "rules": {"seam_allowance_included": True},
            }
        )

        self.assertIsNone(intent["rules"]["one_way_fabric"])
        self.assertIn("one_way_fabric", intent["missing_fields"])

    def test_clarification_request_matches_schema_for_missing_fields(self) -> None:
        intent = normalize_user_intent({"file_id": "file_uploaded"})
        request = build_clarification_request(intent)

        self.assertIsNotNone(request)
        validate_clarification_request(request)
        self.assertTrue(request["blocking"])
        fields = [question["field"] for question in request["questions"]]
        self.assertIn("fabric_width", fields)
        self.assertIn("unit", fields)
        self.assertIn("one_way_fabric", fields)

    def test_no_clarification_request_when_input_is_complete(self) -> None:
        intent = normalize_user_intent(
            {
                "file_id": "file_uploaded",
                "unit": "cm",
                "fabric_width": 150,
                "rules": {"seam_allowance_included": False, "one_way_fabric": False},
            }
        )

        self.assertIsNone(build_clarification_request(intent))


if __name__ == "__main__":
    unittest.main()
