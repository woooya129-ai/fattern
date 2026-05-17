"""Small JSON Schema subset validator for MCP tool inputs."""

from __future__ import annotations

import re
from typing import Any


class ToolValidationError(ValueError):
    pass


def validate_input(schema: dict[str, Any], value: Any) -> None:
    _validate(schema, value, schema)


def _validate(schema: dict[str, Any], value: Any, root: dict[str, Any]) -> None:
    if "$ref" in schema:
        _validate(_resolve_ref(root, schema["$ref"]), value, root)
        return

    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(expected_type, value):
        raise ToolValidationError("input schema validation failed")

    if "const" in schema and value != schema["const"]:
        raise ToolValidationError("input schema validation failed")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolValidationError("input schema validation failed")
    if "pattern" in schema and isinstance(value, str) and re.fullmatch(schema["pattern"], value) is None:
        raise ToolValidationError("input schema validation failed")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if min_length is not None and len(value) < min_length:
            raise ToolValidationError("input schema validation failed")
        if max_length is not None and len(value) > max_length:
            raise ToolValidationError("input schema validation failed")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            raise ToolValidationError("input schema validation failed")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(value) < min_items:
            raise ToolValidationError("input schema validation failed")
        if max_items is not None and len(value) > max_items:
            raise ToolValidationError("input schema validation failed")
        if schema.get("uniqueItems") and len({repr(item) for item in value}) != len(value):
            raise ToolValidationError("input schema validation failed")
        item_schema = schema.get("items")
        if item_schema is not None:
            for item in value:
                _validate(item_schema, item, root)

    if isinstance(value, dict):
        required = schema.get("required", ())
        for field in required:
            if field not in value:
                raise ToolValidationError("input schema validation failed")
        properties = schema.get("properties", {})
        property_names = schema.get("propertyNames")
        if isinstance(property_names, dict):
            for field in value:
                _validate(property_names, field, root)
        if schema.get("additionalProperties") is False:
            for field in value:
                if field not in properties:
                    raise ToolValidationError("input schema validation failed")
        elif isinstance(schema.get("additionalProperties"), dict):
            additional_schema = schema["additionalProperties"]
            for field, field_value in value.items():
                if field not in properties:
                    _validate(additional_schema, field_value, root)
        for field, field_schema in properties.items():
            if field in value:
                _validate(field_schema, value[field], root)


def _matches_type(expected_type: str | list[str], value: Any) -> bool:
    expected = expected_type if isinstance(expected_type, list) else [expected_type]
    return any(_matches_single_type(item, value) for item in expected)


def _matches_single_type(expected_type: str, value: Any) -> bool:
    if expected_type == "null":
        return value is None
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    raise ToolValidationError("input schema validation failed")


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ToolValidationError("input schema validation failed")
    current: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise ToolValidationError("input schema validation failed")
        current = current[part]
    if not isinstance(current, dict):
        raise ToolValidationError("input schema validation failed")
    return current
