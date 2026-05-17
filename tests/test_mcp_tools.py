import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from base64 import b64encode
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
                "create_job",
                "register_input_file",
                "parse_dxf",
                "extract_pattern_pieces",
                "calculate_piece_metrics",
                "estimate_marker_layout",
                "render_marker_svg",
                "get_job_status",
                "export_artifacts",
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

    def _create_rectangle_metrics(self) -> tuple[str, str]:
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
        return job_id, metrics_response["metrics_id"]

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


if __name__ == "__main__":
    unittest.main()
