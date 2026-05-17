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
        "unit_hint": {"type": ["string", "null"], "enum": ["mm", "cm", "inch", None], "default": "cm"},
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
        "unit": {"type": "string", "enum": ["mm", "cm", "inch"], "default": "cm"},
        "curve_flattening_tolerance": {"type": "number", "minimum": 0.01, "default": 0.2},
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
        "fabric_width_unit": {"type": "string", "enum": ["mm", "cm", "inch"], "default": "cm"},
        "rotation_allowed_degrees": {
            "type": "array",
            "items": {"type": "integer", "enum": [0, 90, 180, 270]},
            "minItems": 1,
            "uniqueItems": True,
            "default": [0, 180],
        },
        "clearance": {"type": "number", "minimum": 0, "default": 0.2},
        "one_way_fabric": {"type": ["boolean", "null"], "default": None},
        "grainline_status": {"type": "string", "enum": ["present", "missing", "unknown"], "default": "unknown"},
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

TOOL_DEFINITIONS = (
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
        "description": "Create a piece set from parsed closed LWPOLYLINE candidates.",
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
        "description": "Render a stored marker layout as SVG when a renderer is available.",
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
)

TOOL_SCHEMAS = {tool["name"]: tool["inputSchema"] for tool in TOOL_DEFINITIONS}


def list_tool_definitions() -> list[dict]:
    return deepcopy(list(TOOL_DEFINITIONS))
