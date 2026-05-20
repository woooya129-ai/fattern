import csv
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from base64 import b64encode
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.jobs import JobStore, SecurityError, resolve_workspace_file
from fattern.mcp import McpToolRegistry, McpToolRuntime, FatternMcpServer


FIXTURE_DIR = ROOT / "tests" / "fixtures"
ID_RE = re.compile(r"^(job|file|dxf_parse|piece_set|metrics|layout|artifact)_[a-z0-9_-]{1,72}$")


class McpToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="fattern-mcp-test-")
        self.store = JobStore(Path(self.temp_dir) / "jobs")
        self.registry = McpToolRegistry(self.store)
        self.server = FatternMcpServer(self.registry)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tools_list_exposes_implemented_tool_schemas_only(self) -> None:
        response = self.server.tools_list()
        names = {tool["name"] for tool in response["tools"]}

        self.assertEqual(
            names,
            {
                "get_estimation_questionnaire",
                "create_job",
                "register_input_file",
                "estimate_workspace_dxf",
                "parse_dxf",
                "extract_pattern_pieces",
                "calculate_piece_metrics",
                "estimate_marker_layout",
                "render_marker_svg",
                "get_job_status",
                "export_artifacts",
                "calculate_marker_yield",
            },
        )
        for tool in response["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertNotIn("shell", tool["name"])
            self.assertNotIn("subprocess", tool["name"])

    def test_runtime_and_server_share_registry_tool_definitions(self) -> None:
        server_names = {tool["name"] for tool in self.server.tools_list()["tools"]}
        runtime_names = {tool["name"] for tool in McpToolRuntime(self.store).list_tools()}

        self.assertEqual(server_names, runtime_names)
        self.assertIn("estimate_marker_layout", runtime_names)
        self.assertIn("render_marker_svg", runtime_names)
        self.assertIn("get_job_status", runtime_names)
        self.assertIn("export_artifacts", runtime_names)
        self.assertIn("calculate_marker_yield", runtime_names)
        self.assertIn("estimate_workspace_dxf", runtime_names)

    def test_get_estimation_questionnaire_returns_fabric_width_presets(self) -> None:
        response = self.registry.call_tool("get_estimation_questionnaire", {"schema_version": "1.0"})

        self.assertEqual(response["errors"], [])
        fields = [question["field"] for question in response["questions"]]
        self.assertIn("fabric_width", fields)
        self.assertIn("size_ratio", fields)
        self.assertIn("spacing", fields)
        self.assertIn("allowed_rotation", fields)
        self.assertIn("grainline_required", fields)
        self.assertIn("nap_direction", fields)
        self.assertIn("shrinkage_percent", fields)
        self.assertIn("fabric_type", fields)
        self.assertIn("seam_allowance", fields)
        self.assertNotIn("dxf_unit_hint", fields)
        self.assertNotIn("grainline_status", fields)
        self.assertNotIn("seam_allowance_width", fields)
        self.assertGreaterEqual(len(response["fabric_width_presets"]), 5)

    def test_validation_failure_returns_tool_validation_failed(self) -> None:
        response = self.registry.call_tool(
            "create_job",
            {"schema_version": "1.0", "job_name": "sample", "unexpected": True},
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_invalid_unit_returns_tool_validation_failed_before_lookup(self) -> None:
        response = self.registry.call_tool(
            "calculate_piece_metrics",
            {
                "schema_version": "1.0",
                "job_id": "job_valid",
                "piece_set_id": "piece_set_valid",
                "unit": "meter",
            },
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_path_like_ids_are_rejected_by_schema_validation(self) -> None:
        rejected_file_ids = [
            r"C:\outside\file.dxf",
            "../outside.dxf",
            "file:///outside.dxf",
            r"\\server\share\file.dxf",
            "file_valid:stream",
        ]
        for file_id in rejected_file_ids:
            with self.subTest(file_id=file_id):
                response = self.registry.call_tool(
                    "parse_dxf",
                    {
                        "schema_version": "1.0",
                        "job_id": "job_valid",
                        "file_id": file_id,
                        "unit_hint": "cm",
                    },
                )
                self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_parse_dxf_rejects_path_field(self) -> None:
        response = self.registry.call_tool(
            "parse_dxf",
            {
                "schema_version": "1.0",
                "job_id": "job_valid",
                "file_id": "file_valid",
                "unit_hint": "cm",
                "path": "sample.dxf",
            },
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_create_job_returns_opaque_id_without_workspace_uri(self) -> None:
        response = self.registry.call_tool("create_job", {"schema_version": "1.0", "job_name": "sample"})

        self.assertRegex(response["job_id"], ID_RE)
        self.assertNotIn("workspace_uri", response)
        self.assertNotIn(str(self.store.root), json.dumps(response))

    def test_register_input_file_returns_file_id_without_accepting_paths(self) -> None:
        job_id = self._create_job()
        content = b64encode((FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes()).decode("ascii")

        response = self.registry.call_tool(
            "register_input_file",
            {"schema_version": "1.0", "job_id": job_id, "file_name": "sample.dxf", "content_base64": content},
        )

        serialized = json.dumps(response)
        self.assertEqual(response["errors"], [])
        self.assertRegex(response["file_id"], ID_RE)
        self.assertTrue(response["file_id"].startswith("file_"))
        self.assertNotIn("path", serialized.lower())
        self.assertNotIn(str(self.store.root), serialized)

    def test_register_input_file_rejects_invalid_base64(self) -> None:
        job_id = self._create_job()

        response = self.registry.call_tool(
            "register_input_file",
            {"schema_version": "1.0", "job_id": job_id, "file_name": "sample.dxf", "content_base64": "not_base64"},
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_estimate_workspace_dxf_returns_run_links_and_output_files(self) -> None:
        workspace = Path(self.temp_dir) / "workspace"
        input_dir = workspace / "input"
        input_dir.mkdir(parents=True)
        shutil.copyfile(FIXTURE_DIR / "rectangle_lwpolyline.dxf", input_dir / "sample.dxf")
        output_root = Path(self.temp_dir) / "runs"
        registry = McpToolRegistry(
            self.store,
            workspace_root=workspace,
            output_root=output_root,
            web_base_url="http://127.0.0.1:8765",
            persist_runs=True,
        )

        response = registry.call_tool(
            "estimate_workspace_dxf",
            {
                "schema_version": "1.0",
                "relative_path": "input/sample.dxf",
                "fabric_width": 10,
                "unit": "cm",
            },
        )

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["workspace_relative_path"], "input/sample.dxf")
        self.assertIn("run_id", response)
        self.assertIn("web_url", response)
        self.assertIn("preview_url", response)
        run_dir = Path(response["output_dir"])
        self.assertTrue(run_dir.is_dir())
        self.assertTrue((run_dir / "marker_preview.svg").is_file())
        self.assertTrue((run_dir / "marker_report.md").is_file())
        self.assertTrue((run_dir / "marker_report.pdf").is_file())
        self.assertTrue((run_dir / "report.csv").is_file())
        self.assertTrue((run_dir / "result.json").is_file())
        self.assertTrue((run_dir / "run_summary.txt").is_file())

    def test_estimate_workspace_dxf_rejects_unsafe_paths(self) -> None:
        workspace = Path(self.temp_dir) / "workspace"
        workspace.mkdir()
        registry = McpToolRegistry(self.store, workspace_root=workspace)
        rejected = ["../outside.dxf", str((workspace / "sample.dxf").resolve()), "input/sample.txt"]
        for relative_path in rejected:
            with self.subTest(relative_path=relative_path):
                response = registry.call_tool(
                    "estimate_workspace_dxf",
                    {
                        "schema_version": "1.0",
                        "relative_path": relative_path,
                        "fabric_width": 10,
                        "unit": "cm",
                    },
                )
                self.assertIn(response["errors"][0]["code"], {"INVALID_WORKSPACE_PATH", "UNSUPPORTED_FILE_TYPE"})

    def test_register_input_file_rejects_path_like_file_name(self) -> None:
        job_id = self._create_job()
        content = b64encode(b"0\nEOF\n").decode("ascii")

        response = self.registry.call_tool(
            "register_input_file",
            {"schema_version": "1.0", "job_id": job_id, "file_name": "../sample.dxf", "content_base64": content},
        )

        self.assertEqual(response["errors"][0]["code"], "INVALID_FILE_NAME")

    def test_wrapper_happy_path_uses_server_mapping(self) -> None:
        job_id = self._create_job()
        register_response = self.registry.call_tool(
            "register_input_file",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "file_name": "sample.dxf",
                "content_base64": b64encode((FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes()).decode("ascii"),
            },
        )
        file_id = register_response["file_id"]

        parse_response = self.registry.call_tool(
            "parse_dxf",
            {"schema_version": "1.0", "job_id": job_id, "file_id": file_id, "unit_hint": "cm"},
        )
        self.assertEqual(parse_response["errors"], [])
        self.assertRegex(parse_response["dxf_parse_id"], ID_RE)
        self.assertTrue(parse_response["dxf_parse_id"].startswith("dxf_parse_"))
        self.assertEqual(parse_response["entity_summary"]["entity_count"], 1)
        self.assertEqual(parse_response["layer_audit"][0]["layer"], "OUTLINE")
        self.assertEqual(parse_response["layer_audit"][0]["entity_counts"], {"PIECE_CANDIDATE": 1})
        self.assertNotIn("points", json.dumps(parse_response))

        extract_response = self.registry.call_tool(
            "extract_pattern_pieces",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "dxf_parse_id": parse_response["dxf_parse_id"],
                "extraction_mode": "closed_polylines_only",
                "outline_layer_names": ["OUTLINE"],
                "grainline_layer_names": [],
            },
        )
        self.assertEqual(extract_response["errors"], [])
        self.assertRegex(extract_response["piece_set_id"], ID_RE)
        self.assertEqual(extract_response["piece_summary"][0]["piece_id"], "piece_0001")
        self.assertIsNone(extract_response["piece_summary"][0]["piece_name"])

        metrics_response = self.registry.call_tool(
            "calculate_piece_metrics",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "piece_set_id": extract_response["piece_set_id"],
                "unit": "cm",
            },
        )
        self.assertEqual(metrics_response["errors"], [])
        self.assertRegex(metrics_response["metrics_id"], ID_RE)
        self.assertAlmostEqual(metrics_response["total_area"], 12.0)
        self.assertEqual(metrics_response["piece_metrics"][0]["bbox"], {"width": 4.0, "height": 3.0})

    def test_calculate_piece_metrics_applies_seam_allowance_width(self) -> None:
        job_id, piece_set_id = self._create_rectangle_piece_set()

        response = self.registry.call_tool(
            "calculate_piece_metrics",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "piece_set_id": piece_set_id,
                "unit": "cm",
                "seam_allowance_width": 1.0,
            },
        )

        self.assertEqual(response["errors"], [])
        self.assertEqual(response["warnings"][0]["code"], "SEAM_ALLOWANCE_ESTIMATED")
        self.assertAlmostEqual(response["total_area"], 30.0)
        self.assertEqual(response["piece_metrics"][0]["bbox"], {"width": 6.0, "height": 5.0})
        self.assertAlmostEqual(response["piece_metrics"][0]["seam_allowance_width"], 1.0)

    def test_calculate_piece_metrics_autoscales_dxf_unit(self) -> None:
        job_id = self._create_job()
        piece_set_id = self.store.store_piece_set(
            job_id,
            (
                self._candidate(((0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0))),
            ),
        )

        response = self.registry.call_tool(
            "calculate_piece_metrics",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "piece_set_id": piece_set_id,
                "unit": "cm",
                "dxf_unit_hint": "auto",
                "fabric_width": 100.0,
                "fabric_width_unit": "cm",
            },
        )

        self.assertEqual(response["errors"], [])
        self.assertEqual(response["dxf_unit"], "mm")
        self.assertAlmostEqual(response["unit_scale"], 0.1)
        self.assertEqual(response["warnings"][0]["code"], "DXF_UNIT_AUTOSCALE_APPLIED")
        self.assertEqual(response["piece_metrics"][0]["bbox"], {"width": 40.0, "height": 30.0})

    def test_estimate_marker_layout_returns_layout_id_and_engine_values(self) -> None:
        job_id, metrics_id = self._create_rectangle_metrics()

        response = self.registry.call_tool(
            "estimate_marker_layout",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "metrics_id": metrics_id,
                "fabric_width": 10.0,
                "fabric_width_unit": "cm",
                "rotation_allowed_degrees": [0, 180],
                "clearance": 0.2,
            },
        )

        self.assertEqual(response["errors"], [])
        self.assertRegex(response["layout_id"], ID_RE)
        self.assertTrue(response["layout_id"].startswith("layout_"))
        self.assertEqual(response["marker_length"], 3.0)
        self.assertAlmostEqual(response["efficiency"], 0.4)
        self.assertEqual(response["layout_summary"][0]["piece_id"], "piece_0001")
        self.assertEqual(response["validity"]["within_fabric_width"], True)
        self.assertEqual(response["validity"]["no_overlap"], True)

    def test_estimate_marker_layout_blocks_missing_grainline_for_one_way_fabric(self) -> None:
        job_id, metrics_id = self._create_rectangle_metrics()

        response = self.registry.call_tool(
            "estimate_marker_layout",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "metrics_id": metrics_id,
                "fabric_width": 10.0,
                "fabric_width_unit": "cm",
                "rotation_allowed_degrees": [0, 180],
                "clearance": 0.2,
                "one_way_fabric": True,
                "grainline_status": "missing",
            },
        )
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})

        self.assertEqual(response["errors"][0]["code"], "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC")
        self.assertNotIn("layout_id", response)
        self.assertEqual(status["object_counts"]["layouts"], 0)

    def test_estimate_marker_layout_blocks_required_missing_grainline(self) -> None:
        job_id, metrics_id = self._create_rectangle_metrics()

        response = self.registry.call_tool(
            "estimate_marker_layout",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "metrics_id": metrics_id,
                "fabric_width": 10.0,
                "fabric_width_unit": "cm",
                "rotation_allowed_degrees": [0],
                "clearance": 0.2,
                "grainline_status": "missing",
                "grainline_required": True,
            },
        )
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})

        self.assertEqual(response["errors"][0]["code"], "MISSING_GRAINLINE_REQUIRED")
        self.assertNotIn("layout_id", response)
        self.assertEqual(status["object_counts"]["layouts"], 0)

    def test_estimate_marker_layout_applies_cuttable_spacing_and_nap_policy(self) -> None:
        job_id, metrics_id = self._create_rectangle_metrics()

        response = self.registry.call_tool(
            "estimate_marker_layout",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "metrics_id": metrics_id,
                "fabric_width": 10.0,
                "cuttable_width": 9.0,
                "fabric_width_unit": "cm",
                "rotation_allowed_degrees": [0, 180],
                "clearance": 0.2,
                "spacing": 0.0,
                "nap_direction": "one_way",
            },
        )

        self.assertEqual(response["errors"], [])
        self.assertEqual(response["fabric_width"], 9.0)
        self.assertEqual(response["clearance"], 0.0)
        self.assertEqual(response["rotation_allowed_degrees"], [0])
        self.assertIn("layout_id", response)

    def test_estimate_marker_layout_does_not_store_blocked_layout(self) -> None:
        job_id, metrics_id = self._create_rectangle_metrics()

        response = self.registry.call_tool(
            "estimate_marker_layout",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "metrics_id": metrics_id,
                "fabric_width": 2.0,
                "fabric_width_unit": "cm",
                "rotation_allowed_degrees": [0, 180],
                "clearance": 0.2,
            },
        )
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})

        self.assertEqual(response["errors"][0]["code"], "FABRIC_WIDTH_EXCEEDED")
        self.assertNotIn("layout_id", response)
        self.assertEqual(status["object_counts"]["layouts"], 0)

    def test_render_marker_svg_requires_existing_layout_id_and_does_not_leak_paths(self) -> None:
        job_id = self._create_job()

        response = self.registry.call_tool(
            "render_marker_svg",
            {"schema_version": "1.0", "job_id": job_id, "layout_id": "layout_missing"},
        )

        self.assertEqual(response["errors"][0]["code"], "LAYOUT_NOT_FOUND")
        self.assertNotIn(str(self.store.root), json.dumps(response))
        self.assertNotIn(self.temp_dir, json.dumps(response))

    def test_render_marker_svg_registers_svg_artifact_without_leaking_path(self) -> None:
        job_id, layout_id = self._create_rectangle_layout()

        response = self.registry.call_tool(
            "render_marker_svg",
            {"schema_version": "1.0", "job_id": job_id, "layout_id": layout_id},
        )

        serialized = json.dumps(response)
        self.assertEqual(response["errors"], [])
        self.assertEqual(response["warnings"], [])
        self.assertTrue(response["rendered"])
        self.assertTrue(response["artifact_id"].startswith("artifact_"))
        artifact = self.store.get_artifact(job_id, response["artifact_id"])
        self.assertEqual(artifact.file_name, "marker_preview.svg")
        self.assertIn("<svg", artifact.path.read_text(encoding="utf-8"))
        self.assertNotIn("svg_uri", response)
        self.assertNotIn(str(self.store.root), serialized)
        self.assertNotIn(self.temp_dir, serialized)

    def test_get_job_status_returns_counts_without_workspace_details(self) -> None:
        job_id, layout_id = self._create_rectangle_layout()

        response = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})
        serialized = json.dumps(response)

        self.assertEqual(response["errors"], [])
        self.assertEqual(response["stage"], "layout_estimated")
        self.assertEqual(response["object_counts"]["files"], 1)
        self.assertEqual(response["object_counts"]["layouts"], 1)
        self.assertNotIn(layout_id, serialized)
        self.assertNotIn("workspace", serialized)
        self.assertNotIn(str(self.store.root), serialized)
        self.assertNotIn(self.temp_dir, serialized)

    def test_get_job_status_rejects_guessable_missing_job_without_leaking_paths(self) -> None:
        response = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": "job_guessable"})

        serialized = json.dumps(response)
        self.assertEqual(response["errors"][0]["code"], "JOB_NOT_FOUND")
        self.assertNotIn(str(self.store.root), serialized)
        self.assertNotIn(self.temp_dir, serialized)

    def test_export_artifacts_returns_archive_artifact_id_without_path(self) -> None:
        job_id = self._create_job()
        artifact_id = self.store.register_artifact(
            job_id,
            "result.json",
            '{"marker_length": 3.0}',
            media_type="application/json",
        )

        response = self.registry.call_tool(
            "export_artifacts",
            {"schema_version": "1.0", "job_id": job_id, "artifact_ids": [artifact_id], "archive_format": "zip"},
        )
        serialized = json.dumps(response)

        self.assertEqual(response["errors"], [])
        self.assertRegex(response["archive_artifact_id"], ID_RE)
        self.assertTrue(response["archive_artifact_id"].startswith("artifact_"))
        self.assertEqual(response["archive_format"], "zip")
        self.assertEqual(response["artifact_count"], 1)
        self.assertGreater(response["size_bytes"], 0)
        self.assertNotIn("path", serialized.lower())
        self.assertNotIn("uri", serialized.lower())
        self.assertNotIn(str(self.store.root), serialized)
        self.assertNotIn(self.temp_dir, serialized)

    def test_export_artifacts_uses_manifest_allowlist(self) -> None:
        job_id = self._create_job()

        response = self.registry.call_tool(
            "export_artifacts",
            {"schema_version": "1.0", "job_id": job_id, "artifact_ids": ["artifact_missing"]},
        )

        self.assertEqual(response["errors"][0]["code"], "ARTIFACT_NOT_FOUND")
        self.assertNotIn(str(self.store.root), json.dumps(response))

    def test_export_artifacts_rejects_path_like_artifact_ids_before_lookup(self) -> None:
        job_id = self._create_job()
        response = self.registry.call_tool(
            "export_artifacts",
            {"schema_version": "1.0", "job_id": job_id, "artifact_ids": ["../artifact.json"]},
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_calculate_marker_yield_rejects_path_like_pattern_file_id(self) -> None:
        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(pattern_file_id="../sample.dxf"),
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_calculate_marker_yield_rejects_cuttable_width_larger_than_fabric_width(self) -> None:
        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(cuttable_width=11.0),
        )

        self.assertEqual(response["errors"][0]["code"], "INVALID_CUTTABLE_WIDTH")

    def test_calculate_marker_yield_rejects_invalid_size_ratio_shape(self) -> None:
        invalid_cases = (
            {"M": 0},
            {"../M": 1},
        )
        for size_ratio in invalid_cases:
            with self.subTest(size_ratio=size_ratio):
                response = self.registry.call_tool(
                    "calculate_marker_yield",
                    self._marker_yield_request(size_ratio=size_ratio),
                )

                self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_calculate_marker_yield_rejects_shrinkage_percent_at_100(self) -> None:
        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(shrinkage_percent=100),
        )

        self.assertEqual(response["errors"][0]["code"], "INVALID_SHRINKAGE_PERCENT")

    def test_calculate_marker_yield_blocks_one_way_180_rotation_before_chain(self) -> None:
        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(nap_direction="one_way", allowed_rotation=[0, 180]),
        )

        self.assertEqual(response["errors"][0]["code"], "NAP_ROTATION_NOT_ALLOWED")

    def test_calculate_marker_yield_blocks_unknown_nap_direction_before_chain(self) -> None:
        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(nap_direction="unknown"),
        )

        self.assertEqual(response["errors"][0]["code"], "NAP_DIRECTION_UNKNOWN")

    def test_calculate_marker_yield_warns_knit_stretch_not_applied_when_direction_is_explicit(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(
                pattern_file_id=file_id,
                fabric_type="knit",
                stretch_direction="lengthwise",
            ),
        )

        self.assertEqual(response["status"], "completed")
        self.assertIn("STRETCH_DIRECTION_NOT_APPLIED", [warning["code"] for warning in response["warnings"]])

    def test_calculate_marker_yield_maps_one_way_nap_to_grainline_policy(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(pattern_file_id=file_id, nap_direction="one_way", allowed_rotation=[0]),
        )
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["stopped_at"], "extract_pattern_pieces")
        self.assertEqual(response["errors"][0]["code"], "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC")
        self.assertEqual(response["tool_calls"], ["parse_dxf", "extract_pattern_pieces"])
        self.assertEqual(status["object_counts"]["metrics"], 0)
        self.assertEqual(status["object_counts"]["layouts"], 0)

    def test_calculate_marker_yield_rejects_negative_seam_allowance_fallback(self) -> None:
        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(seam_allowance={"status": "excluded", "fallback_width": -1.0}),
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_calculate_marker_yield_rejects_zero_quote_rounding_unit(self) -> None:
        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(allowance_policy={"mode": "fast_quote", "rounding_unit": 0}),
        )

        self.assertEqual(response["errors"][0]["code"], "TOOL_VALIDATION_FAILED")

    def test_calculate_marker_yield_happy_path_returns_exportable_artifacts(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(
                pattern_file_id=file_id,
                cuttable_width=9.0,
                size_ratio={"M": 2},
                shrinkage_percent=3,
                seam_allowance={"status": "included", "fallback_width": 1.0},
            ),
        )

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["job_id"], job_id)
        self.assertEqual(response["pattern_file_id"], file_id)
        self.assertEqual(response["stopped_at"], "completed")
        self.assertEqual(
            response["tool_calls"],
            [
                "parse_dxf",
                "extract_pattern_pieces",
                "calculate_piece_metrics",
                "estimate_marker_layout",
                "render_marker_svg",
            ],
        )
        self.assertEqual(response["errors"], [])
        self.assertEqual(response["layout"]["marker_length"], 3.0)
        self.assertEqual(
            [warning["code"] for warning in response["warnings"]],
            [
                "CUTTABLE_WIDTH_APPLIED",
                "GRAINLINE_NOT_DETECTED",
                "SIZE_RATIO_BASE_SIZE_REPLICATED",
                "SHRINKAGE_PERCENT_NOT_APPLIED",
                "REPORT_CSV_PARTIAL_FIELDS",
            ],
        )
        self.assertEqual(
            sorted(response["artifact_ids"]),
            ["marker_preview_svg", "marker_report_md", "marker_report_pdf", "report_csv", "result_json"],
        )
        self.assertEqual(len(response["export_artifact_ids"]), 5)
        result_artifact = self.store.get_artifact(job_id, response["artifact_ids"]["result_json"])
        report_artifact = self.store.get_artifact(job_id, response["artifact_ids"]["marker_report_md"])
        pdf_artifact = self.store.get_artifact(job_id, response["artifact_ids"]["marker_report_pdf"])
        csv_artifact = self.store.get_artifact(job_id, response["artifact_ids"]["report_csv"])

        self.assertEqual(result_artifact.file_name, "result.json")
        self.assertEqual(report_artifact.file_name, "marker_report.md")
        self.assertEqual(pdf_artifact.file_name, "marker_report.pdf")
        self.assertTrue(pdf_artifact.path.read_bytes().startswith(b"%PDF-1.4"))
        self.assertEqual(csv_artifact.file_name, "report.csv")
        self.assertIn('"status": "completed"', result_artifact.path.read_text(encoding="utf-8"))
        self.assertIn("- marker_length: 3 cm", report_artifact.path.read_text(encoding="utf-8"))
        csv_text = csv_artifact.path.read_text(encoding="utf-8")
        self.assertIn("piece_id,piece_name,size,quantity,area_mm2", csv_text)
        rows = list(csv.DictReader(StringIO(csv_text)))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["size"] for row in rows}, {"M"})
        self.assertEqual({row["quantity"] for row in rows}, {"1"})
        self.assertTrue(all(row["area_mm2"] for row in rows))
        self.assertTrue(all(row["bbox_width_mm"] for row in rows))
        self.assertTrue(all(row["bbox_height_mm"] for row in rows))
        self.assertEqual(response["partial_csv_fields"], ["piece_name", "grainline_status"])
        self.assertEqual(
            next(warning["message"] for warning in response["warnings"] if warning["code"] == "REPORT_CSV_PARTIAL_FIELDS"),
            "report.csv leaves unavailable piece metadata fields empty: piece_name, grainline_status.",
        )
        self.assertIn("`REPORT_CSV_PARTIAL_FIELDS`", report_artifact.path.read_text(encoding="utf-8"))
        export_response = self.registry.call_tool(
            "export_artifacts",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "artifact_ids": response["export_artifact_ids"],
                "archive_format": "zip",
            },
        )
        self.assertEqual(export_response["errors"], [])
        archive = self.store.get_artifact(job_id, export_response["archive_artifact_id"])
        with zipfile.ZipFile(archive.path) as handle:
            names = set(handle.namelist())
        self.assertTrue(any(name.endswith("_result.json") for name in names))
        self.assertTrue(any(name.endswith("_marker_preview.svg") for name in names))
        self.assertTrue(any(name.endswith("_marker_report.md") for name in names))
        self.assertTrue(any(name.endswith("_marker_report.pdf") for name in names))
        self.assertTrue(any(name.endswith("_report.csv") for name in names))

    def test_calculate_marker_yield_excludes_small_invalid_closed_contour(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(job_id, "small-invalid-contour.dxf", _small_invalid_contour_dxf())

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(pattern_file_id=file_id, size_ratio={}),
        )

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["errors"], [])
        self.assertIn("SMALL_INVALID_CONTOUR_EXCLUDED", [warning["code"] for warning in response["warnings"]])
        self.assertEqual([piece["piece_id"] for piece in response["layout"]["layout_summary"]], ["piece_0001"])

    def test_calculate_marker_yield_applies_piece_quantity_without_size_ratio(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(
                pattern_file_id=file_id,
                size_ratio={},
                piece_quantity={"piece_0001": 2},
            ),
        )
        csv_artifact = self.store.get_artifact(job_id, response["artifact_ids"]["report_csv"])
        rows = list(csv.DictReader(StringIO(csv_artifact.path.read_text(encoding="utf-8"))))

        self.assertEqual(response["status"], "completed")
        self.assertEqual(len(response["layout"]["layout_summary"]), 2)
        self.assertEqual([warning["code"] for warning in response["warnings"]], [
            "GRAINLINE_NOT_DETECTED",
            "PIECE_QUANTITY_APPLIED",
            "REPORT_CSV_PARTIAL_FIELDS",
        ])
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["quantity"] for row in rows}, {"1"})

    def test_calculate_marker_yield_returns_quote_decision_layer(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(
                pattern_file_id=file_id,
                size_ratio={},
                allowance_policy={
                    "mode": "fast_quote",
                    "rounding_unit": 0.5,
                    "base_buffer_percent": 10.0,
                    "cutting_loss_percent": 0.0,
                    "end_loss_length": 1.0,
                    "fabric_defect_buffer_percent": 0.0,
                    "unknown_risk_buffer_percent": 0.0,
                    "apply_warning_penalty": False,
                },
            ),
        )
        report_artifact = self.store.get_artifact(job_id, response["artifact_ids"]["marker_report_md"])
        report_text = report_artifact.path.read_text(encoding="utf-8")

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["minimum_yield"], {
            "marker_length": 3.0,
            "unit": "cm",
            "source": "deterministic_marker_layout",
        })
        self.assertAlmostEqual(response["allowance_breakdown"]["base_buffer"], 0.3)
        self.assertAlmostEqual(response["allowance_breakdown"]["end_loss"], 1.0)
        self.assertAlmostEqual(response["allowance_breakdown"]["rounding"], 0.2)
        self.assertAlmostEqual(response["quote_yield"]["final_yield"], 4.5)
        self.assertEqual(response["quote_yield"]["rounding_rule"], "round_up_0.5cm")
        self.assertEqual(response["confidence"]["grade"], "B")
        self.assertIn("## Quote Summary", report_text)
        self.assertIn("- quote_yield: 4.5 cm", report_text)

    def test_calculate_marker_yield_with_persistence_returns_run_urls(self) -> None:
        store = JobStore(Path(self.temp_dir) / "persist-jobs")
        registry = McpToolRegistry(
            store,
            output_root=Path(self.temp_dir) / "persist-output",
            web_base_url="http://127.0.0.1:8765",
            persist_runs=True,
        )
        job_id = registry.call_tool("create_job", {"schema_version": "1.0", "job_name": "persist"})["job_id"]
        file_id = store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(pattern_file_id=file_id, size_ratio={}),
        )

        self.assertEqual(response["status"], "completed")
        self.assertIn("run_id", response)
        self.assertTrue(response["web_url"].endswith(f"/runs/{response['run_id']}"))
        self.assertTrue(response["preview_url"].endswith("/marker_preview.svg"))
        self.assertTrue(response["report_url"].endswith("/marker_report.pdf"))
        self.assertTrue((Path(response["output_dir"]) / "run_summary.txt").is_file())
        result_json = json.loads((Path(response["output_dir"]) / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result_json["run_id"], response["run_id"])

    def test_calculate_marker_yield_stops_on_blocker_without_following_tools(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(pattern_file_id=file_id, grainline_required=True),
        )
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["stopped_at"], "extract_pattern_pieces")
        self.assertEqual(response["errors"][0]["code"], "MISSING_GRAINLINE_REQUIRED")
        self.assertEqual(response["tool_calls"], ["parse_dxf", "extract_pattern_pieces"])
        self.assertNotIn("calculate_piece_metrics", response["tool_calls"])
        self.assertEqual(status["object_counts"]["layouts"], 0)
        self.assertEqual(status["object_counts"]["metrics"], 0)
        self.assertEqual(sorted(response["artifact_ids"]), ["result_json"])

    def test_calculate_marker_yield_blocks_woven_without_grainline_before_metrics(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(pattern_file_id=file_id, fabric_type="woven"),
        )
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["stopped_at"], "extract_pattern_pieces")
        self.assertEqual(response["errors"][0]["code"], "MISSING_GRAINLINE_FOR_WOVEN")
        self.assertEqual(response["tool_calls"], ["parse_dxf", "extract_pattern_pieces"])
        self.assertEqual(status["object_counts"]["metrics"], 0)

    def test_calculate_marker_yield_blocks_one_way_without_grainline_even_when_not_required(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(
                pattern_file_id=file_id,
                nap_direction="one_way",
                grainline_required=False,
            ),
        )
        status = self.registry.call_tool("get_job_status", {"schema_version": "1.0", "job_id": job_id})

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["stopped_at"], "extract_pattern_pieces")
        self.assertEqual(response["errors"][0]["code"], "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC")
        self.assertEqual(response["tool_calls"], ["parse_dxf", "extract_pattern_pieces"])
        self.assertEqual(status["object_counts"]["metrics"], 0)

    def test_extract_pattern_pieces_detects_grainline_candidates_without_counting_internal_lines(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(job_id, "semantic.dxf", _semantic_dxf())
        parse_response = self.registry.call_tool(
            "parse_dxf",
            {"schema_version": "1.0", "job_id": job_id, "file_id": file_id, "unit_hint": "cm"},
        )

        response = self.registry.call_tool(
            "extract_pattern_pieces",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "dxf_parse_id": parse_response["dxf_parse_id"],
                "extraction_mode": "closed_polylines_only",
                "outline_layer_names": [],
                "grainline_layer_names": [],
            },
        )

        self.assertEqual(response["errors"], [])
        self.assertEqual(response["piece_summary"][0]["piece_name"], "Front")
        self.assertEqual(response["piece_summary"][0]["size"], "M")
        self.assertEqual(response["piece_summary"][0]["has_grainline"], True)
        self.assertEqual(response["piece_summary"][0]["grainline_layer"], "GRAINLINE")
        grainline_audit = next(item for item in response["layer_audit"] if item["layer"] == "GRAINLINE")
        self.assertEqual(grainline_audit["mapping_status"], "deterministic_candidate")
        self.assertEqual(grainline_audit["grainline_confidence"], 0.8)
        self.assertIn("GRAINLINE_LAYER_CANDIDATE_DETECTED", [warning["code"] for warning in response["warnings"]])

    def test_layer_audit_flags_numeric_aama_astm_candidate_as_unverified(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(job_id, "numeric-layer.dxf", _numeric_layer_dxf())
        parse_response = self.registry.call_tool(
            "parse_dxf",
            {"schema_version": "1.0", "job_id": job_id, "file_id": file_id, "unit_hint": "cm"},
        )

        response = self.registry.call_tool(
            "extract_pattern_pieces",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "dxf_parse_id": parse_response["dxf_parse_id"],
                "extraction_mode": "closed_polylines_only",
                "outline_layer_names": [],
                "grainline_layer_names": [],
            },
        )

        numeric_audit = next(item for item in response["layer_audit"] if item["layer"] == "7")
        self.assertEqual(response["errors"], [])
        self.assertEqual(response["piece_summary"][0]["has_grainline"], True)
        self.assertEqual(numeric_audit["mapping_status"], "aama_astm_candidate_unverified")
        self.assertEqual(numeric_audit["grainline_confidence"], 0.6)
        self.assertIn("AAMA_ASTM_LAYER_MAPPING_UNVERIFIED", [warning["code"] for warning in response["warnings"]])

    def test_extract_pattern_pieces_accepts_connected_line_loop_fallback(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(job_id, "line-loop.dxf", _line_loop_dxf())
        parse_response = self.registry.call_tool(
            "parse_dxf",
            {"schema_version": "1.0", "job_id": job_id, "file_id": file_id, "unit_hint": "cm"},
        )

        response = self.registry.call_tool(
            "extract_pattern_pieces",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "dxf_parse_id": parse_response["dxf_parse_id"],
                "extraction_mode": "connect_lines",
                "outline_layer_names": [],
                "grainline_layer_names": [],
            },
        )

        self.assertEqual(response["errors"], [])
        self.assertEqual(response["piece_summary"][0]["piece_id"], "piece_0001")
        self.assertIn("LINE_LOOP_CONTOUR_CONNECTED", [warning["code"] for warning in response["warnings"]])
        self.assertIn("EXTRACTION_MODE_FALLBACK", [warning["code"] for warning in response["warnings"]])

    def test_calculate_marker_yield_allows_one_way_when_grainline_is_detected(self) -> None:
        job_id = self._create_job()
        file_id = self.store.register_input_file(job_id, "semantic.dxf", _semantic_dxf())

        response = self.registry.call_tool(
            "calculate_marker_yield",
            self._marker_yield_request(
                pattern_file_id=file_id,
                nap_direction="one_way",
                allowed_rotation=[0],
                shrinkage_percent=3,
            ),
        )
        csv_artifact = self.store.get_artifact(job_id, response["artifact_ids"]["report_csv"])
        rows = list(csv.DictReader(StringIO(csv_artifact.path.read_text(encoding="utf-8"))))

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["layout"]["grainline_status"], "present")
        self.assertIn("SHRINKAGE_APPLIED", [warning["code"] for warning in response["warnings"]])
        self.assertEqual(rows[0]["piece_name"], "Front")
        self.assertEqual(rows[0]["size"], "M")
        self.assertEqual(rows[0]["grainline_status"], "present")

    def test_register_input_file_rejects_path_tokens_and_unsupported_types(self) -> None:
        job_id = self._create_job()
        rejected_names = [
            "../sample.dxf",
            r"C:\sample.dxf",
            "file:///sample.dxf",
            r"\\server\share\sample.dxf",
            "sample.dxf:ads",
            "sample.txt",
        ]
        for name in rejected_names:
            with self.subTest(name=name):
                with self.assertRaises(SecurityError):
                    self.store.register_input_file(job_id, name, b"0\nEOF\n")

    def test_canonical_containment_blocks_outside_file(self) -> None:
        job = self.store.create_job("sample")
        outside_file = Path(self.temp_dir) / "outside.dxf"
        outside_file.write_text("0\nEOF\n", encoding="utf-8")

        with self.assertRaises(SecurityError) as raised:
            resolve_workspace_file(job.workspace_root, outside_file)

        self.assertEqual(raised.exception.code, "PATH_CONTAINMENT_FAILED")
        self.assertNotIn(str(outside_file), raised.exception.public_message)

    def test_symlink_escape_is_blocked_when_supported(self) -> None:
        job = self.store.create_job("sample")
        outside_file = Path(self.temp_dir) / "outside-symlink.dxf"
        outside_file.write_text("0\nEOF\n", encoding="utf-8")
        link_path = job.workspace_root / "inputs" / "link.dxf"
        try:
            link_path.symlink_to(outside_file)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation not available: {exc}")

        with self.assertRaises(SecurityError) as raised:
            resolve_workspace_file(job.workspace_root, link_path)

        self.assertIn(raised.exception.code, {"PATH_CONTAINMENT_FAILED", "FILE_ACCESS_BLOCKED"})

    def test_hardlink_escape_is_blocked_when_supported(self) -> None:
        job = self.store.create_job("sample")
        outside_file = Path(self.temp_dir) / "outside-hardlink.dxf"
        outside_file.write_text("0\nEOF\n", encoding="utf-8")
        hardlink_path = job.workspace_root / "inputs" / "hardlink.dxf"
        try:
            os.link(outside_file, hardlink_path)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"hardlink creation not available: {exc}")

        with self.assertRaises(SecurityError) as raised:
            resolve_workspace_file(job.workspace_root, hardlink_path)

        self.assertEqual(raised.exception.code, "FILE_ACCESS_BLOCKED")

    def test_parse_errors_do_not_expose_internal_paths(self) -> None:
        job_id = self._create_job()
        response = self.registry.call_tool(
            "parse_dxf",
            {"schema_version": "1.0", "job_id": job_id, "file_id": "file_missing", "unit_hint": "cm"},
        )

        serialized = json.dumps(response)
        self.assertEqual(response["errors"][0]["code"], "FILE_NOT_FOUND")
        self.assertNotIn(str(self.store.root), serialized)
        self.assertNotIn(self.temp_dir, serialized)

    def _create_job(self) -> str:
        response = self.registry.call_tool("create_job", {"schema_version": "1.0", "job_name": "sample"})
        return response["job_id"]

    def _marker_yield_request(self, **overrides: object) -> dict[str, object]:
        request: dict[str, object] = {
            "schema_version": "1.0",
            "pattern_file_id": "file_valid",
            "fabric_width": 10.0,
            "unit": "cm",
            "size_ratio": {"M": 1},
            "spacing": 0.2,
            "allowed_rotation": [0],
            "grainline_required": False,
            "nap_direction": "two_way",
            "shrinkage_percent": 0,
            "fabric_type": "unknown",
            "seam_allowance": {"status": "included"},
        }
        request.update(overrides)
        return request

    def _create_rectangle_metrics(self) -> tuple[str, str]:
        job_id, piece_set_id = self._create_rectangle_piece_set()
        metrics_response = self.registry.call_tool(
            "calculate_piece_metrics",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "piece_set_id": piece_set_id,
                "unit": "cm",
            },
        )
        self.assertEqual(metrics_response["errors"], [])
        return job_id, metrics_response["metrics_id"]

    def _create_rectangle_piece_set(self) -> tuple[str, str]:
        job_id = self._create_job()
        file_id = self.store.register_input_file(
            job_id,
            "sample.dxf",
            (FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
        )
        parse_response = self.registry.call_tool(
            "parse_dxf",
            {"schema_version": "1.0", "job_id": job_id, "file_id": file_id, "unit_hint": "cm"},
        )
        extract_response = self.registry.call_tool(
            "extract_pattern_pieces",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "dxf_parse_id": parse_response["dxf_parse_id"],
                "extraction_mode": "closed_polylines_only",
                "outline_layer_names": ["OUTLINE"],
                "grainline_layer_names": [],
            },
        )
        self.assertEqual(extract_response["errors"], [])
        return job_id, extract_response["piece_set_id"]

    def _candidate(self, points: tuple[tuple[float, float], ...]):
        from fattern.engine import PolylineCandidate

        return PolylineCandidate(
            piece_id="piece_0001",
            layer="OUTLINE",
            points=points,
            closed=True,
            source_entity_index=1,
            vertex_count=len(points),
        )

    def _create_rectangle_layout(self) -> tuple[str, str]:
        job_id, metrics_id = self._create_rectangle_metrics()
        layout_response = self.registry.call_tool(
            "estimate_marker_layout",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "metrics_id": metrics_id,
                "fabric_width": 10.0,
                "fabric_width_unit": "cm",
                "rotation_allowed_degrees": [0, 180],
                "clearance": 0.2,
            },
        )
        self.assertEqual(layout_response["errors"], [])
        return job_id, layout_response["layout_id"]

def _semantic_dxf() -> str:
    return "\n".join(
        [
            "0", "SECTION",
            "2", "ENTITIES",
            "0", "LWPOLYLINE",
            "8", "piece=Front;size=M",
            "90", "4",
            "70", "1",
            "10", "0",
            "20", "0",
            "10", "4",
            "20", "0",
            "10", "4",
            "20", "3",
            "10", "0",
            "20", "3",
            "0", "LINE",
            "8", "GRAINLINE",
            "10", "2",
            "20", "0.5",
            "11", "2",
            "21", "2.5",
            "0", "TEXT",
            "8", "LABEL",
            "10", "1",
            "20", "1",
            "1", "Front label",
            "0", "ENDSEC",
            "0", "EOF",
        ]
    )


def _numeric_layer_dxf() -> bytes:
    return "\n".join(
        [
            "0", "SECTION",
            "2", "ENTITIES",
            "0", "LWPOLYLINE",
            "8", "OUTLINE",
            "90", "4",
            "70", "1",
            "10", "0",
            "20", "0",
            "10", "4",
            "20", "0",
            "10", "4",
            "20", "3",
            "10", "0",
            "20", "3",
            "0", "LINE",
            "8", "7",
            "10", "2",
            "20", "0.5",
            "11", "2",
            "21", "2.5",
            "0", "ENDSEC",
            "0", "EOF",
        ]
    ).encode("utf-8")


def _line_loop_dxf() -> bytes:
    return "\n".join(
        [
            "0", "SECTION",
            "2", "HEADER",
            "9", "$ACADVER",
            "1", "AC1009",
            "0", "ENDSEC",
            "0", "SECTION",
            "2", "ENTITIES",
            "0", "LINE",
            "8", "OUTLINE",
            "10", "0",
            "20", "0",
            "11", "4",
            "21", "0",
            "0", "LINE",
            "8", "OUTLINE",
            "10", "4",
            "20", "0",
            "11", "4",
            "21", "3",
            "0", "LINE",
            "8", "OUTLINE",
            "10", "4",
            "20", "3",
            "11", "0",
            "21", "3",
            "0", "LINE",
            "8", "OUTLINE",
            "10", "0",
            "20", "3",
            "11", "0",
            "21", "0",
            "0", "ENDSEC",
            "0", "EOF",
        ]
    ).encode("utf-8")


def _small_invalid_contour_dxf() -> bytes:
    return "\n".join(
        [
            "0", "SECTION",
            "2", "ENTITIES",
            "0", "LWPOLYLINE",
            "8", "OUTLINE",
            "90", "4",
            "70", "1",
            "10", "0",
            "20", "0",
            "10", "4",
            "20", "0",
            "10", "4",
            "20", "3",
            "10", "0",
            "20", "3",
            "0", "LWPOLYLINE",
            "8", "MARK",
            "90", "4",
            "70", "1",
            "10", "10",
            "20", "10",
            "10", "10.2",
            "20", "10.2",
            "10", "10",
            "20", "10.2",
            "10", "10.2",
            "20", "10",
            "0", "ENDSEC",
            "0", "EOF",
        ]
    ).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
