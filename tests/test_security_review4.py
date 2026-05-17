import inspect
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import fattern.jobs.store as job_store_module
from fattern.jobs import JobStore, SecurityError
from fattern.mcp import McpToolRegistry
from fattern.mcp.schemas import TOOL_SCHEMAS

SCHEMA_DIR = ROOT / "schemas"

TOOL_INPUT_DEFS = {
    "create_job": "create_job_input",
    "register_input_file": "register_input_file_input",
    "parse_dxf": "parse_dxf_input",
    "extract_pattern_pieces": "extract_pattern_pieces_input",
    "calculate_piece_metrics": "calculate_piece_metrics_input",
    "estimate_marker_layout": "estimate_marker_layout_input",
    "render_marker_svg": "render_marker_svg_input",
    "get_job_status": "get_job_status_input",
    "export_artifacts": "export_artifacts_input",
}


class Review4ArtifactPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="fattern-review4-security-test-")
        self.store = JobStore(Path(self.temp_dir) / "jobs")
        self.registry = McpToolRegistry(self.store)
        self.job_id = self.registry.call_tool("create_job", {"schema_version": "1.0", "job_name": "sample"})[
            "job_id"
        ]

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generated_archive_artifact_should_not_be_reexportable_until_nested_zip_policy_exists(self) -> None:
        artifact_id = self.store.register_artifact(
            self.job_id,
            "result.json",
            '{"status": "ok"}',
            media_type="application/json",
        )
        first_export = self.registry.call_tool(
            "export_artifacts",
            {"schema_version": "1.0", "job_id": self.job_id, "artifact_ids": [artifact_id]},
        )
        self.assertEqual(first_export["errors"], [])

        nested_export = self.registry.call_tool(
            "export_artifacts",
            {
                "schema_version": "1.0",
                "job_id": self.job_id,
                "artifact_ids": [first_export["archive_artifact_id"]],
            },
        )

        self.assertNotEqual(nested_export["errors"], [])
        self.assertEqual(nested_export["errors"][0]["code"], "ARTIFACT_NOT_EXPORTABLE")

    def test_register_artifact_declares_size_limit_contract(self) -> None:
        parameters = inspect.signature(JobStore.register_artifact).parameters
        has_max_bytes_parameter = "max_bytes" in parameters
        has_module_limit = any(
            hasattr(job_store_module, name)
            for name in ("MAX_ARTIFACT_BYTES", "DEFAULT_MAX_ARTIFACT_BYTES", "ARTIFACT_MAX_BYTES")
        )

        self.assertTrue(
            has_max_bytes_parameter or has_module_limit,
            "register_artifact has no explicit max-bytes contract.",
        )
        with self.assertRaises(SecurityError) as raised:
            self.store.register_artifact(
                self.job_id,
                "large.json",
                b"12345",
                media_type="application/json",
                max_bytes=4,
            )
        self.assertEqual(raised.exception.code, "ARTIFACT_SIZE_LIMIT_EXCEEDED")

    def test_tool_security_errors_redact_internal_paths_and_trace_text(self) -> None:
        leaked_message = (
            r"Failed reading C:\obs\fattern\jobs\job_secret\logs\secret.json "
            "Traceback SECRET_TOKEN=value"
        )
        self.registry._handlers["get_job_status"] = lambda _arguments: _raise(  # noqa: SLF001
            SecurityError("PATH_CONTAINMENT_FAILED", leaked_message)
        )

        response = self.registry.call_tool(
            "get_job_status",
            {"schema_version": "1.0", "job_id": self.job_id},
        )
        serialized = json.dumps(response)

        self.assertEqual(response["errors"][0]["code"], "FILE_ACCESS_BLOCKED")
        self.assertEqual(response["errors"][0]["message"], "Internal file access failed.")
        for token in ("C:", "fattern", "job_secret", "Traceback", "SECRET_TOKEN", str(self.store.root)):
            self.assertNotIn(token, serialized)

    def test_unhandled_tool_exception_uses_generic_redacted_error(self) -> None:
        self.registry._handlers["get_job_status"] = lambda _arguments: _raise(  # noqa: SLF001
            RuntimeError(r"C:\obs\fattern\jobs\job_secret\secret.txt Traceback SECRET_TOKEN=value")
        )

        response = self.registry.call_tool(
            "get_job_status",
            {"schema_version": "1.0", "job_id": self.job_id},
        )
        serialized = json.dumps(response)

        self.assertEqual(response["errors"][0]["code"], "INTERNAL_TOOL_ERROR")
        self.assertEqual(response["errors"][0]["message"], "Tool execution failed.")
        for token in ("C:", "fattern", "job_secret", "Traceback", "SECRET_TOKEN", str(self.store.root)):
            self.assertNotIn(token, serialized)


class Review4SchemaDriftTests(unittest.TestCase):
    def test_python_tool_schemas_match_json_schema_defs_for_drift_sensitive_fields(self) -> None:
        schema = json.loads((SCHEMA_DIR / "mcp-tools.schema.json").read_text(encoding="utf-8"))
        defs = schema["$defs"]
        tool_name_enum = set(defs["tool_contract"]["properties"]["name"]["enum"])

        self.assertEqual(set(TOOL_SCHEMAS), set(TOOL_INPUT_DEFS))
        self.assertEqual(set(TOOL_INPUT_DEFS), tool_name_enum)

        for tool_name, def_name in TOOL_INPUT_DEFS.items():
            with self.subTest(tool_name=tool_name):
                json_contract = _canonicalize_schema(defs[def_name], defs)
                python_contract = _canonicalize_schema(TOOL_SCHEMAS[tool_name], defs)
                self.assertEqual(python_contract, json_contract)


def _canonicalize_schema(value: Any, defs: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$ref"}:
            return _canonicalize_schema(_resolve_ref(value["$ref"], defs), defs)
        return {key: _canonicalize_schema(value[key], defs) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonicalize_schema(item, defs) for item in value]
    return value


def _resolve_ref(ref: str, defs: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/$defs/"):
        raise AssertionError(f"Unsupported schema ref: {ref}")
    name = ref.removeprefix("#/$defs/")
    if name not in defs:
        raise AssertionError(f"Unknown schema ref: {ref}")
    return defs[name]


def _raise(exc: Exception) -> None:
    raise exc


if __name__ == "__main__":
    unittest.main()
