"""MCP tool definitions exposed through tools/list."""

from __future__ import annotations

from copy import deepcopy

from fattern.schemas import ID_PATTERN

OPAQUE_ID_SCHEMA = {
    "type": "string",
    "minLength": 5,
    "maxLength": 80,
    "pattern": ID_PATTERN,
}

SIZE_RATIO_SCHEMA = {
    "type": "object",
    "propertyNames": {
        "type": "string",
        "minLength": 1,
        "maxLength": 40,
        "pattern": r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$",
    },
    "additionalProperties": {"type": "integer", "minimum": 1},
    "default": {},
}

PIECE_QUANTITY_SCHEMA = {
    "type": "object",
    "propertyNames": {
        "type": "string",
        "minLength": 1,
        "maxLength": 40,
        "pattern": r"^(\*|[A-Za-z0-9][A-Za-z0-9 ._-]{0,39})$",
    },
    "additionalProperties": {"type": "integer", "minimum": 1},
    "default": {},
}

SHRINKAGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["length_percent", "width_percent"],
    "properties": {
        "length_percent": {"type": "number", "minimum": 0, "default": 0},
        "width_percent": {"type": "number", "minimum": 0, "default": 0},
    },
}

ALLOWANCE_POLICY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mode": {"type": "string", "enum": ["fast_quote", "sample_estimate", "bulk_precheck"], "default": "fast_quote"},
        "rounding_unit": {"type": ["number", "null"], "exclusiveMinimum": 0, "default": None},
        "base_buffer_percent": {"type": ["number", "null"], "minimum": 0, "default": None},
        "cutting_loss_percent": {"type": ["number", "null"], "minimum": 0, "default": None},
        "end_loss_length": {"type": ["number", "null"], "minimum": 0, "default": None},
        "fabric_defect_buffer_percent": {"type": ["number", "null"], "minimum": 0, "default": None},
        "unknown_risk_buffer_percent": {"type": ["number", "null"], "minimum": 0, "default": None},
        "apply_warning_penalty": {"type": "boolean", "default": True},
    },
    "default": {},
}

GET_ESTIMATION_QUESTIONNAIRE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
    },
}

CREATE_JOB_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_name"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_name": {"type": "string", "minLength": 1, "maxLength": 120},
        "user_note": {"type": "string", "maxLength": 500, "default": ""},
    },
}

REGISTER_INPUT_FILE_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_id", "file_name", "content_base64"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
        "file_name": {"type": "string", "minLength": 1, "maxLength": 120},
        "content_base64": {
            "type": "string",
            "minLength": 1,
            "maxLength": 14_000_000,
            "pattern": r"^[A-Za-z0-9+/]*={0,2}$",
        },
    },
}

PARSE_DXF_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_id", "file_id", "unit_hint"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
        "file_id": OPAQUE_ID_SCHEMA,
        "unit_hint": {"type": ["string", "null"], "enum": ["auto", "mm", "cm", "m", "inch", "ft", "yd", None], "default": "auto"},
        "layer_profile": {"type": ["string", "null"], "maxLength": 80, "default": None},
    },
}

EXTRACT_PATTERN_PIECES_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_id", "dxf_parse_id", "extraction_mode"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
        "dxf_parse_id": OPAQUE_ID_SCHEMA,
        "extraction_mode": {
            "type": "string",
            "enum": ["closed_polylines_only", "connect_lines", "mixed_entities"],
            "default": "closed_polylines_only",
        },
        "outline_layer_names": {"type": "array", "items": {"type": "string", "maxLength": 120}, "default": []},
        "grainline_layer_names": {"type": "array", "items": {"type": "string", "maxLength": 120}, "default": []},
    },
}

CALCULATE_PIECE_METRICS_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_id", "piece_set_id", "unit"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
        "piece_set_id": OPAQUE_ID_SCHEMA,
        "unit": {"type": "string", "enum": ["mm", "cm", "m", "inch", "ft", "yd"], "default": "cm"},
        "dxf_unit_hint": {"type": "string", "enum": ["auto", "mm", "cm", "m", "inch", "ft", "yd"], "default": "auto"},
        "fabric_width": {"type": ["number", "null"], "minimum": 1, "default": None},
        "fabric_width_unit": {"type": ["string", "null"], "enum": ["mm", "cm", "m", "inch", "ft", "yd", None], "default": None},
        "curve_flattening_tolerance": {"type": "number", "minimum": 0.01, "default": 0.2},
        "seam_allowance_width": {"type": "number", "minimum": 0, "default": 0},
    },
}

ESTIMATE_MARKER_LAYOUT_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "job_id",
        "metrics_id",
        "fabric_width",
        "fabric_width_unit",
        "rotation_allowed_degrees",
        "clearance",
    ],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
        "metrics_id": OPAQUE_ID_SCHEMA,
        "fabric_width": {"type": "number", "minimum": 1},
        "cuttable_width": {"type": ["number", "null"], "minimum": 1, "default": None},
        "fabric_width_unit": {"type": "string", "enum": ["mm", "cm", "m", "inch", "ft", "yd"], "default": "cm"},
        "rotation_allowed_degrees": {
            "type": "array",
            "items": {"type": "integer", "enum": [0, 90, 180, 270]},
            "minItems": 1,
            "uniqueItems": True,
            "default": [0],
        },
        "clearance": {"type": "number", "minimum": 0, "default": 0.2},
        "spacing": {"type": ["number", "null"], "minimum": 0, "default": None},
        "nap_direction": {
            "type": ["string", "null"],
            "enum": ["one_way", "two_way", "none", "no_nap", "not_one_way", "unknown", None],
            "default": None,
        },
        "one_way_fabric": {"type": ["boolean", "null"], "default": None},
        "grainline_status": {"type": "string", "enum": ["present", "missing", "unknown"], "default": "unknown"},
        "grainline_required": {"type": ["boolean", "null"], "default": None},
        "fabric_type": {"type": ["string", "null"], "enum": ["woven", "knit", "unknown", None], "default": None},
    },
}

RENDER_MARKER_SVG_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_id", "layout_id"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
        "layout_id": OPAQUE_ID_SCHEMA,
    },
}

GET_JOB_STATUS_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_id"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
    },
}

EXPORT_ARTIFACTS_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "job_id", "artifact_ids"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "job_id": OPAQUE_ID_SCHEMA,
        "artifact_ids": {"type": "array", "items": OPAQUE_ID_SCHEMA, "minItems": 1, "maxItems": 20},
        "archive_format": {"type": "string", "enum": ["zip"], "default": "zip"},
    },
}

CALCULATE_MARKER_YIELD_INPUT = {
    "type": "object",
    "additionalProperties": False,
    "required": [
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
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "pattern_file_id": OPAQUE_ID_SCHEMA,
        "fabric_width": {"type": "number", "minimum": 1},
        "cuttable_width": {"type": ["number", "null"], "minimum": 1, "default": None},
        "unit": {"type": "string", "enum": ["mm", "cm", "m", "inch", "ft", "yd"]},
        "size_ratio": SIZE_RATIO_SCHEMA,
        "piece_quantity": PIECE_QUANTITY_SCHEMA,
        "spacing": {"type": "number", "minimum": 0, "default": 0},
        "allowed_rotation": {
            "type": "array",
            "items": {"type": "integer", "enum": [0, 90, 180, 270]},
            "minItems": 1,
            "maxItems": 4,
            "uniqueItems": True,
            "default": [0],
        },
        "grainline_required": {"type": "boolean", "default": True},
        "nap_direction": {
            "type": "string",
            "enum": ["one_way", "two_way", "none", "no_nap", "not_one_way", "unknown"],
            "default": "unknown",
        },
        "shrinkage_percent": {"type": "number", "minimum": 0, "default": 0},
        "shrinkage": SHRINKAGE_SCHEMA,
        "fabric_type": {"type": "string", "enum": ["woven", "knit", "unknown"], "default": "unknown"},
        "stretch_direction": {
            "type": ["string", "null"],
            "enum": ["lengthwise", "crosswise", "bias", "unknown", None],
            "default": None,
        },
        "seam_allowance": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status"],
            "properties": {
                "status": {"type": "string", "enum": ["included", "excluded"]},
                "fallback_width": {"type": ["number", "null"], "minimum": 0, "default": None},
            },
        },
        "allowance_policy": ALLOWANCE_POLICY_SCHEMA,
    },
}

TOOL_DEFINITIONS = (
    {
        "name": "get_estimation_questionnaire",
        "description": "Return the setup questionnaire and global fabric-width presets for rough marker estimation.",
        "inputSchema": GET_ESTIMATION_QUESTIONNAIRE_INPUT,
    },
    {
        "name": "create_job",
        "description": "Create an isolated job workspace and return an opaque job ID.",
        "inputSchema": CREATE_JOB_INPUT,
    },
    {
        "name": "register_input_file",
        "description": "Register an input file from base64 content and return an opaque file ID.",
        "inputSchema": REGISTER_INPUT_FILE_INPUT,
    },
    {
        "name": "parse_dxf",
        "description": "Parse a mapped DXF file by file_id and return an entity summary.",
        "inputSchema": PARSE_DXF_INPUT,
    },
    {
        "name": "extract_pattern_pieces",
        "description": "Create a piece set from parsed closed DXF outline candidates.",
        "inputSchema": EXTRACT_PATTERN_PIECES_INPUT,
    },
    {
        "name": "calculate_piece_metrics",
        "description": "Calculate deterministic metrics for an extracted piece set.",
        "inputSchema": CALCULATE_PIECE_METRICS_INPUT,
    },
    {
        "name": "estimate_marker_layout",
        "description": "Estimate a deterministic rough marker layout from stored piece metrics.",
        "inputSchema": ESTIMATE_MARKER_LAYOUT_INPUT,
    },
    {
        "name": "render_marker_svg",
        "description": "Render a stored marker layout as an SVG artifact.",
        "inputSchema": RENDER_MARKER_SVG_INPUT,
    },
    {
        "name": "get_job_status",
        "description": "Return non-sensitive status for an isolated job.",
        "inputSchema": GET_JOB_STATUS_INPUT,
    },
    {
        "name": "export_artifacts",
        "description": "Package manifest-allowlisted job artifacts into a zip artifact.",
        "inputSchema": EXPORT_ARTIFACTS_INPUT,
    },
    {
        "name": "calculate_marker_yield",
        "description": "Run the DXF rough marker workflow from a registered pattern_file_id and return exportable artifacts.",
        "inputSchema": CALCULATE_MARKER_YIELD_INPUT,
    },
)

TOOL_SCHEMAS = {tool["name"]: tool["inputSchema"] for tool in TOOL_DEFINITIONS}


def list_tool_definitions() -> list[dict]:
    return deepcopy(list(TOOL_DEFINITIONS))
