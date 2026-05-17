import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

from fattern.mcp.schemas import TOOL_SCHEMAS
from fattern.schemas import ID_PATTERN

SCHEMA_DIR = ROOT / "schemas"


def load_schema(name: str) -> dict:
    with (SCHEMA_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class SchemaContractTests(unittest.TestCase):
    def test_schema_files_are_valid_json_objects(self) -> None:
        for path in SCHEMA_DIR.glob("*.schema.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(data["type"], "object")

    def test_llm_facing_schemas_are_closed(self) -> None:
        for name in ["user-intent.schema.json", "clarification.schema.json"]:
            schema = load_schema(name)
            self.assertIs(schema["additionalProperties"], False)
            self.assertIn("schema_version", schema["required"])
            self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")

    def test_policy_defaults_are_locked_in_user_intent(self) -> None:
        schema = load_schema("user-intent.schema.json")
        self.assertEqual(schema["properties"]["unit"]["default"], "cm")
        self.assertEqual(schema["properties"]["dxf_unit_hint"]["default"], "auto")
        rules = schema["properties"]["rules"]["properties"]
        self.assertEqual(rules["grainline_status"]["default"], "unknown")
        self.assertEqual(rules["rotation_allowed_degrees"]["default"], [0])
        self.assertEqual(rules["clearance"]["default"], 0.2)
        self.assertIsNone(rules["seam_allowance_included"]["default"])
        self.assertIsNone(rules["seam_allowance_width"]["default"])

    def test_common_opaque_id_pattern(self) -> None:
        schema = load_schema("common.schema.json")
        pattern = schema["$defs"]["opaque_id"]["pattern"]
        self.assertEqual(pattern, ID_PATTERN)
        self.assertRegex("job_abc-123", re.compile(pattern))
        self.assertRegex("dxf_parse_abc-123", re.compile(pattern))
        self.assertRegex("layout_marker_1", re.compile(pattern))
        self.assertIsNone(re.compile(pattern).match("../outside"))
        self.assertIsNone(re.compile(pattern).match("C:/outside"))

    def test_mcp_tool_contracts_are_closed_where_defined(self) -> None:
        schema = load_schema("mcp-tools.schema.json")
        defs = schema["$defs"]
        for name in [
            "create_job_input",
            "get_estimation_questionnaire_input",
            "register_input_file_input",
            "id_only_input",
            "parse_dxf_input",
            "extract_pattern_pieces_input",
            "calculate_piece_metrics_input",
            "estimate_marker_layout_input",
            "render_marker_svg_input",
            "get_job_status_input",
            "export_artifacts_input",
        ]:
            self.assertIs(defs[name]["additionalProperties"], False)

    def test_estimate_marker_layout_input_locks_policy_defaults(self) -> None:
        schema = load_schema("mcp-tools.schema.json")
        metrics_input = schema["$defs"]["calculate_piece_metrics_input"]["properties"]
        layout_input = schema["$defs"]["estimate_marker_layout_input"]["properties"]
        self.assertEqual(metrics_input["dxf_unit_hint"]["default"], "auto")
        self.assertEqual(metrics_input["seam_allowance_width"]["default"], 0)
        self.assertEqual(layout_input["fabric_width_unit"]["default"], "cm")
        self.assertEqual(layout_input["rotation_allowed_degrees"]["default"], [0])
        self.assertEqual(layout_input["clearance"]["default"], 0.2)
        self.assertEqual(layout_input["grainline_status"]["enum"], ["present", "missing", "unknown"])

    def test_mcp_python_schema_uses_shared_opaque_id_pattern(self) -> None:
        schema = load_schema("mcp-tools.schema.json")
        self.assertEqual(schema["$defs"]["opaque_id"]["pattern"], ID_PATTERN)

        for tool_schema in TOOL_SCHEMAS.values():
            for field, field_schema in tool_schema["properties"].items():
                if field.endswith("_id") and field_schema.get("pattern") is not None:
                    self.assertEqual(field_schema["pattern"], ID_PATTERN)


if __name__ == "__main__":
    unittest.main()
