import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

from fattern.mcp.schemas import TOOL_SCHEMAS
from fattern.mcp.validation import validate_input
from fattern.schemas import ID_PATTERN

SCHEMA_DIR = ROOT / "schemas"


def load_schema(name: str) -> dict:
    with (SCHEMA_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def inline_opaque_id_refs(node: object, defs: dict) -> object:
    if isinstance(node, dict):
        if node == {"$ref": "#/$defs/opaque_id"}:
            return defs["opaque_id"]
        return {key: inline_opaque_id_refs(value, defs) for key, value in node.items()}
    if isinstance(node, list):
        return [inline_opaque_id_refs(value, defs) for value in node]
    return node


class SchemaContractTests(unittest.TestCase):
    def test_schema_files_are_valid_json_objects(self) -> None:
        for path in SCHEMA_DIR.glob("*.schema.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(data["type"], "object")

    def test_llm_facing_schemas_are_closed(self) -> None:
        for name in ["user-intent.schema.json", "clarification.schema.json", "answers.schema.json"]:
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
            "estimate_workspace_dxf_input",
            "id_only_input",
            "parse_dxf_input",
            "extract_pattern_pieces_input",
            "calculate_piece_metrics_input",
            "estimate_marker_layout_input",
            "render_marker_svg_input",
            "get_job_status_input",
            "export_artifacts_input",
            "calculate_marker_yield_input",
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
        self.assertEqual(layout_input["cuttable_width"]["default"], None)
        self.assertEqual(layout_input["spacing"]["default"], None)
        self.assertEqual(layout_input["nap_direction"]["enum"], ["one_way", "two_way", "none", "no_nap", "not_one_way", "unknown", None])
        self.assertEqual(layout_input["grainline_required"]["default"], None)
        self.assertEqual(layout_input["fabric_type"]["enum"], ["woven", "knit", "unknown", None])

    def test_mcp_python_schema_uses_shared_opaque_id_pattern(self) -> None:
        schema = load_schema("mcp-tools.schema.json")
        self.assertEqual(schema["$defs"]["opaque_id"]["pattern"], ID_PATTERN)

        for tool_schema in TOOL_SCHEMAS.values():
            for field, field_schema in tool_schema["properties"].items():
                if field.endswith("_id") and field_schema.get("pattern") is not None:
                    self.assertEqual(field_schema["pattern"], ID_PATTERN)

    def test_calculate_marker_yield_input_locks_v04_contract(self) -> None:
        schema = load_schema("mcp-tools.schema.json")
        defs = schema["$defs"]
        marker_input = defs["calculate_marker_yield_input"]
        marker_props = marker_input["properties"]

        self.assertIs(marker_input["additionalProperties"], False)
        self.assertEqual(
            marker_input["required"],
            [
                "schema_version",
                "pattern_file_id",
                "fabric_width",
                "unit",
                "size_ratio",
                "spacing",
                "allowed_rotation",
                "grainline_required",
                "nap_direction",
                "shrinkage_percent",
                "fabric_type",
                "seam_allowance",
            ],
        )
        self.assertEqual(marker_props["pattern_file_id"], {"$ref": "#/$defs/opaque_id"})
        self.assertEqual(
            marker_props["size_ratio"],
            {
                "type": "object",
                "propertyNames": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 40,
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$",
                },
                "additionalProperties": {"type": "integer", "minimum": 1},
                "default": {},
            },
        )
        self.assertEqual(
            marker_props["piece_quantity"],
            {
                "type": "object",
                "propertyNames": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 40,
                    "pattern": "^(\\*|[A-Za-z0-9][A-Za-z0-9 ._-]{0,39})$",
                },
                "additionalProperties": {"type": "integer", "minimum": 1},
                "default": {},
            },
        )
        self.assertEqual(marker_props["allowed_rotation"]["items"]["enum"], [0, 90, 180, 270])
        self.assertEqual(marker_props["allowed_rotation"]["minItems"], 1)
        self.assertEqual(marker_props["allowed_rotation"]["maxItems"], 4)
        self.assertIs(marker_props["allowed_rotation"]["uniqueItems"], True)
        self.assertEqual(
            marker_props["nap_direction"]["enum"],
            ["one_way", "two_way", "none", "no_nap", "not_one_way", "unknown"],
        )
        self.assertEqual(marker_props["seam_allowance"]["properties"]["status"]["enum"], ["included", "excluded"])
        self.assertEqual(
            marker_props["seam_allowance"]["properties"]["fallback_width"],
            {"type": ["number", "null"], "minimum": 0, "default": None},
        )
        self.assertEqual(marker_props["shrinkage_percent"]["minimum"], 0)
        self.assertNotIn("maximum", marker_props["shrinkage_percent"])
        self.assertEqual(marker_props["shrinkage"]["properties"]["length_percent"]["minimum"], 0)
        self.assertEqual(marker_props["shrinkage"]["properties"]["width_percent"]["minimum"], 0)
        self.assertEqual(marker_props["stretch_direction"]["enum"], ["lengthwise", "crosswise", "bias", "unknown", None])
        self.assertEqual(marker_props["allowance_policy"]["properties"]["mode"]["enum"], ["fast_quote", "sample_estimate", "bulk_precheck"])
        self.assertEqual(marker_props["allowance_policy"]["properties"]["rounding_unit"]["exclusiveMinimum"], 0)
        self.assertEqual(marker_props["allowance_policy"]["properties"]["apply_warning_penalty"]["default"], True)

        self.assertEqual(inline_opaque_id_refs(marker_input, defs), TOOL_SCHEMAS["calculate_marker_yield"])

    def test_estimate_workspace_dxf_schema_matches_python_tool_schema(self) -> None:
        schema = load_schema("mcp-tools.schema.json")
        self.assertEqual(schema["$defs"]["estimate_workspace_dxf_input"], TOOL_SCHEMAS["estimate_workspace_dxf"])

    def test_answers_schema_tracks_calculate_marker_yield_without_pattern_file_id(self) -> None:
        mcp_schema = load_schema("mcp-tools.schema.json")
        marker_input = mcp_schema["$defs"]["calculate_marker_yield_input"]
        answers_schema = load_schema("answers.schema.json")

        self.assertEqual(
            answers_schema["required"],
            [field for field in marker_input["required"] if field != "pattern_file_id"],
        )
        self.assertNotIn("pattern_file_id", answers_schema["properties"])
        for field in answers_schema["required"]:
            self.assertEqual(answers_schema["properties"][field], marker_input["properties"][field])
        self.assertEqual(answers_schema["properties"]["cuttable_width"], marker_input["properties"]["cuttable_width"])
        self.assertEqual(answers_schema["properties"]["allowance_policy"], marker_input["properties"]["allowance_policy"])

    def test_readme_answers_example_validates_against_canonical_schema(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r"```json\n(?P<body>\{.*?\})\n```", readme, flags=re.S)
        self.assertIsNotNone(match)
        example = json.loads(match.group("body"))

        validate_input(load_schema("answers.schema.json"), example)


if __name__ == "__main__":
    unittest.main()
