import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.jobs import JobStore
from fattern.jobs.security import ALLOWED_ARTIFACT_SUFFIXES
from fattern.mcp import McpToolRegistry
from fattern.orchestration.chain import (
    ChainResultValidationError,
    ReportValidationError,
    adapt_marker_yield_request,
    execute_marker_estimation,
    execute_marker_yield_request,
    validate_final_report,
    validate_stopped_at,
)
from fattern.orchestration.intent import normalize_user_intent


FIXTURE_DIR = ROOT / "tests" / "fixtures"


def intent(
    *,
    fabric_width: float = 10.0,
    one_way_fabric: bool = False,
    grainline_status: str = "unknown",
    grainline_required: bool = False,
) -> dict:
    return normalize_user_intent(
        {
            "dxf_file": "sample.dxf",
            "unit": "cm",
            "fabric_width": fabric_width,
            "rules": {
                "seam_allowance_included": True,
                "one_way_fabric": one_way_fabric,
                "grainline_status": grainline_status,
                "grainline_required": grainline_required,
                "rotation_allowed_degrees": [0, 180],
                "clearance": 0.2,
            },
        }
    )


def self_intersecting_dxf() -> str:
    return "\n".join(
        [
            "0",
            "SECTION",
            "2",
            "HEADER",
            "9",
            "$ACADVER",
            "1",
            "AC1027",
            "0",
            "ENDSEC",
            "0",
            "SECTION",
            "2",
            "ENTITIES",
            "0",
            "LWPOLYLINE",
            "8",
            "OUTLINE",
            "90",
            "4",
            "70",
            "1",
            "10",
            "0",
            "20",
            "0",
            "10",
            "2",
            "20",
            "2",
            "10",
            "0",
            "20",
            "2",
            "10",
            "2",
            "20",
            "0",
            "0",
            "ENDSEC",
            "0",
            "EOF",
        ]
    )


class OrchestrationChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="fattern-orch-test-")
        self.store = JobStore(Path(self.temp_dir) / "jobs")
        self.registry = McpToolRegistry(self.store)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_happy_path_runs_tool_chain_and_returns_artifact_ids(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["stopped_at"], "completed")
        self.assertEqual(
            result["tool_calls"],
            [
                "create_job",
                "register_input_file",
                "parse_dxf",
                "extract_pattern_pieces",
                "calculate_piece_metrics",
                "estimate_marker_layout",
            ],
        )
        self.assertTrue(result["layout_id"].startswith("layout_"))
        self.assertTrue(result["svg_artifact_id"].startswith("artifact_"))
        self.assertTrue(result["report_artifact_id"].startswith("artifact_"))
        self.assertEqual(result["layout"]["marker_length"], 3.0)
        self.assertAlmostEqual(result["layout"]["efficiency"], 0.4)

    def test_parse_failed_blocker_stops_before_extract(self) -> None:
        result = execute_marker_estimation(
            intent(),
            dxf_file_name="broken.dxf",
            dxf_content="0\nSECTION\n",
            registry=self.registry,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "parse_dxf")
        self.assertEqual(result["errors"][0]["code"], "PARSE_FAILED")
        self.assertEqual(result["tool_calls"], ["create_job", "register_input_file", "parse_dxf"])
        self.assertNotIn("dxf_parse_id", result)
        self.assertNotIn("svg_artifact_id", result)

    def test_no_pattern_pieces_blocker_stops_at_extract(self) -> None:
        result = self._run(FIXTURE_DIR / "open_lwpolyline.dxf")

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "extract_pattern_pieces")
        self.assertEqual(result["errors"][0]["code"], "NO_PATTERN_PIECES_FOUND")
        self.assertEqual(result["tool_calls"], ["create_job", "register_input_file", "parse_dxf", "extract_pattern_pieces"])
        self.assertEqual([warning["code"] for warning in result["warnings"]], ["NON_CLOSED_CONTOUR"])
        self.assertNotIn("piece_set_id", result)
        self.assertNotIn("svg_artifact_id", result)

    def test_self_intersection_blocker_stops_at_metrics(self) -> None:
        result = execute_marker_estimation(
            intent(),
            dxf_file_name="self-intersection.dxf",
            dxf_content=self_intersecting_dxf(),
            registry=self.registry,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "calculate_piece_metrics")
        self.assertEqual(result["errors"][0]["code"], "SELF_INTERSECTION")
        self.assertEqual(
            result["tool_calls"],
            ["create_job", "register_input_file", "parse_dxf", "extract_pattern_pieces", "calculate_piece_metrics"],
        )
        self.assertNotIn("metrics_id", result)
        self.assertNotIn("svg_artifact_id", result)

    def test_fabric_width_exceeded_stops_at_layout_without_artifacts(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf", user_intent=intent(fabric_width=2.0))
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": result["job_id"]})

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "estimate_marker_layout")
        self.assertEqual(result["errors"][0]["code"], "FABRIC_WIDTH_EXCEEDED")
        self.assertEqual(status["object_counts"]["layouts"], 0)
        self.assertEqual(status["object_counts"]["artifacts"], 0)
        self.assertNotIn("svg_artifact_id", result)

    def test_missing_grainline_on_one_way_fabric_stops_at_layout(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf", user_intent=intent(one_way_fabric=True))
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": result["job_id"]})

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "estimate_marker_layout")
        self.assertEqual(result["errors"][0]["code"], "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC")
        self.assertEqual(status["object_counts"]["layouts"], 0)
        self.assertNotIn("svg_artifact_id", result)

    def test_explicit_grainline_status_is_passed_to_layout(self) -> None:
        result = self._run(
            FIXTURE_DIR / "rectangle_lwpolyline.dxf",
            user_intent=intent(one_way_fabric=True, grainline_status="present"),
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["layout"]["grainline_status"], "present")
        self.assertIs(result["layout"]["one_way_fabric"], True)

    def test_missing_fields_do_not_start_tool_chain(self) -> None:
        missing = normalize_user_intent({"dxf_file": "sample.dxf"})
        result = execute_marker_estimation(
            missing,
            dxf_file_name="sample.dxf",
            dxf_content=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
            registry=self.registry,
        )

        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["stopped_at"], "normalize_user_intent")
        self.assertEqual(result["tool_calls"], [])
        self.assertIn("fabric_width", result["missing_fields"])
        self.assertNotIn("job_id", result)

    def test_artifacts_are_registered_and_response_does_not_leak_workspace_paths(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf")
        svg = self.store.get_artifact(result["job_id"], result["svg_artifact_id"])
        report = self.store.get_artifact(result["job_id"], result["report_artifact_id"])
        serialized = json.dumps(result)

        self.assertEqual(svg.file_name, "marker_preview.svg")
        self.assertEqual(svg.media_type, "image/svg+xml")
        self.assertIn(svg.path.suffix, ALLOWED_ARTIFACT_SUFFIXES)
        self.assertIn("<svg", svg.path.read_text(encoding="utf-8"))
        self.assertEqual(report.file_name, "marker_report.md")
        self.assertEqual(report.media_type, "text/markdown")
        self.assertIn(report.path.suffix, ALLOWED_ARTIFACT_SUFFIXES)
        self.assertIn("- marker_length: 3 cm", report.path.read_text(encoding="utf-8"))
        self.assertNotIn(str(self.store.root), serialized)
        self.assertNotIn(self.temp_dir, serialized)
        self.assertNotIn("workspace", serialized.lower())

    def test_final_report_numbers_match_chain_result_and_layout_result(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf")
        layout = self.store.get_layout(result["job_id"], result["layout_id"])
        report = self.store.get_artifact(result["job_id"], result["report_artifact_id"]).path.read_text(
            encoding="utf-8"
        )

        validate_final_report(result, layout, report)

        self.assertEqual(result["layout"]["marker_length"], layout.marker_length)
        self.assertEqual(result["layout"]["efficiency"], layout.efficiency)
        self.assertEqual(result["layout"]["total_piece_area"], layout.total_piece_area)
        self.assertIn("- marker_length: 3 cm", report)
        self.assertIn("- efficiency: 0.4", report)
        self.assertIn("- total_piece_area: 12 cm^2", report)

    def test_final_report_guard_rejects_number_not_from_layout_result(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf")
        layout = self.store.get_layout(result["job_id"], result["layout_id"])
        report = self.store.get_artifact(result["job_id"], result["report_artifact_id"]).path.read_text(
            encoding="utf-8"
        )
        tampered = report.replace("- marker_length: 3 cm", "- marker_length: 30 cm")

        with self.assertRaises(ReportValidationError):
            validate_final_report(result, layout, tampered)

    def test_final_report_guard_rejects_chain_layout_number_mismatch(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf")
        layout = self.store.get_layout(result["job_id"], result["layout_id"])
        report = self.store.get_artifact(result["job_id"], result["report_artifact_id"]).path.read_text(
            encoding="utf-8"
        )
        tampered_result = dict(result)
        tampered_layout = dict(result["layout"])
        tampered_layout["efficiency"] = 0.99
        tampered_result["layout"] = tampered_layout

        with self.assertRaises(ReportValidationError):
            validate_final_report(tampered_result, layout, report)

    def test_final_report_guard_rejects_piece_id_not_from_tool_output(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf")
        layout = self.store.get_layout(result["job_id"], result["layout_id"])
        report = self.store.get_artifact(result["job_id"], result["report_artifact_id"]).path.read_text(
            encoding="utf-8"
        )
        tampered = report.replace("| piece\\_0001 |", "| invented\\_piece |")

        with self.assertRaises(ReportValidationError):
            validate_final_report(result, layout, tampered)

    def test_final_report_guard_rejects_certain_yield_language(self) -> None:
        result = self._run(FIXTURE_DIR / "rectangle_lwpolyline.dxf")
        layout = self.store.get_layout(result["job_id"], result["layout_id"])
        report = self.store.get_artifact(result["job_id"], result["report_artifact_id"]).path.read_text(
            encoding="utf-8"
        )

        with self.assertRaises(ReportValidationError):
            validate_final_report(result, layout, report + "\n확정 요척: 3 cm\n")

    def test_stopped_at_values_are_enum_validated(self) -> None:
        allowed = [
            "completed",
            "adapt_marker_yield_request",
            "normalize_user_intent",
            "create_job",
            "register_input_file",
            "parse_dxf",
            "extract_pattern_pieces",
            "calculate_piece_metrics",
            "estimate_marker_layout",
            "render_marker_report",
        ]

        for stopped_at in allowed:
            with self.subTest(stopped_at=stopped_at):
                self.assertEqual(validate_stopped_at(stopped_at), stopped_at)

        with self.assertRaises(ChainResultValidationError):
            validate_stopped_at("invented_stage")

    def _run(self, path: Path, *, user_intent: dict | None = None) -> dict:
        return execute_marker_estimation(
            user_intent or intent(),
            dxf_file_name=path.name,
            dxf_content=path.read_bytes(),
            registry=self.registry,
        )


class HighLevelMarkerYieldAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="fattern-orch-high-level-test-")
        self.store = JobStore(Path(self.temp_dir) / "jobs")
        self.registry = McpToolRegistry(self.store)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_adapter_maps_cuttable_width_spacing_and_one_way_policy(self) -> None:
        result = adapt_marker_yield_request(
            {
                "pattern_file_id": "file_uploaded",
                "fabric_width": 1470,
                "cuttable_width": 1450,
                "unit": "mm",
                "spacing": 5,
                "allowed_rotation": [0],
                "nap_direction": "one_way",
                "seam_allowance": {"status": "included"},
            }
        )

        self.assertEqual(result["status"], "ready")
        user_intent = result["user_intent"]
        self.assertEqual(user_intent["fabric"], {"width": 1450, "width_unit": "mm"})
        self.assertEqual(user_intent["rules"]["clearance"], 5)
        self.assertIs(user_intent["rules"]["one_way_fabric"], True)
        self.assertEqual(user_intent["rules"]["rotation_allowed_degrees"], [0])
        self.assertEqual(
            [warning["code"] for warning in result["warnings"]],
            ["CUTTABLE_WIDTH_USED", "NAP_DIRECTION_ONE_WAY_MAPPED", "SPACING_MAPPED_TO_CLEARANCE"],
        )

    def test_high_level_pattern_file_id_only_blocks_before_tool_chain(self) -> None:
        result = execute_marker_yield_request(
            {
                "pattern_file_id": "file_uploaded",
                "fabric_width": 10,
                "unit": "cm",
                "allowed_rotation": [0],
                "nap_direction": "none",
                "grainline_required": False,
                "seam_allowance": {"status": "included"},
            },
            registry=self.registry,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "adapt_marker_yield_request")
        self.assertEqual(result["tool_calls"], [])
        self.assertEqual(result["errors"][0]["code"], "PATTERN_FILE_MAPPING_UNRESOLVED")
        self.assertNotIn("job_id", result)

    def test_high_level_size_ratio_is_blocked_until_chain_contract_exists(self) -> None:
        result = execute_marker_yield_request(
            {
                "pattern_file_id": "file_uploaded",
                "fabric_width": 10,
                "unit": "cm",
                "size_ratio": {"S": 1, "M": 2},
                "allowed_rotation": [0],
                "nap_direction": "none",
                "grainline_required": False,
                "seam_allowance": {"status": "included"},
            },
            dxf_file_name="rectangle_lwpolyline.dxf",
            dxf_content=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
            registry=self.registry,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "adapt_marker_yield_request")
        self.assertEqual(result["tool_calls"], [])
        self.assertEqual(result["errors"][0]["code"], "SIZE_RATIO_UNSUPPORTED_BY_CHAIN")

    def test_high_level_adapter_blocks_fields_it_cannot_apply(self) -> None:
        blocked_fields = {
            "piece_quantity": {"piece_0001": 2},
            "shrinkage": {"length_percent": 3, "width_percent": 0},
            "stretch_direction": "lengthwise",
        }

        for field, value in blocked_fields.items():
            with self.subTest(field=field):
                result = execute_marker_yield_request(
                    {
                        "pattern_file_id": "file_uploaded",
                        "fabric_width": 10,
                        "unit": "cm",
                        "allowed_rotation": [0],
                        "nap_direction": "none",
                        "grainline_required": False,
                        "seam_allowance": {"status": "included"},
                        field: value,
                    },
                    dxf_file_name="rectangle_lwpolyline.dxf",
                    dxf_content=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
                    registry=self.registry,
                )

                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["stopped_at"], "adapt_marker_yield_request")
                self.assertEqual(result["tool_calls"], [])
                self.assertEqual(result["errors"][0]["code"], f"{field.upper()}_UNSUPPORTED_BY_CHAIN")

    def test_high_level_grainline_required_non_one_way_reaches_layout_policy(self) -> None:
        result = execute_marker_yield_request(
            {
                "pattern_file_id": "file_uploaded",
                "fabric_width": 10,
                "unit": "cm",
                "allowed_rotation": [0],
                "nap_direction": "none",
                "grainline_required": True,
                "seam_allowance": {"status": "included"},
            },
            dxf_file_name="rectangle_lwpolyline.dxf",
            dxf_content=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
            registry=self.registry,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stopped_at"], "estimate_marker_layout")
        self.assertEqual(result["errors"][0]["code"], "MISSING_GRAINLINE_REQUIRED")
        self.assertEqual(
            result["tool_calls"],
            [
                "create_job",
                "register_input_file",
                "parse_dxf",
                "extract_pattern_pieces",
                "calculate_piece_metrics",
                "estimate_marker_layout",
            ],
        )

    def test_high_level_request_runs_existing_chain_when_mapping_is_safe(self) -> None:
        result = execute_marker_yield_request(
            {
                "pattern_file_id": "file_uploaded",
                "fabric_width": 10,
                "unit": "cm",
                "spacing": 0.2,
                "allowed_rotation": [0],
                "nap_direction": "none",
                "grainline_required": False,
                "seam_allowance": {"status": "included"},
            },
            dxf_file_name="rectangle_lwpolyline.dxf",
            dxf_content=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
            registry=self.registry,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            result["tool_calls"],
            [
                "create_job",
                "register_input_file",
                "parse_dxf",
                "extract_pattern_pieces",
                "calculate_piece_metrics",
                "estimate_marker_layout",
            ],
        )
        self.assertEqual(result["layout"]["fabric_width"], 10)
        self.assertEqual(result["layout"]["clearance"], 0.2)
        self.assertEqual(result["warnings"][0]["code"], "SPACING_MAPPED_TO_CLEARANCE")


if __name__ == "__main__":
    unittest.main()
