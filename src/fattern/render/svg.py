"""Safe SVG renderer for marker layout results."""

from __future__ import annotations

from collections.abc import Sequence
from xml.etree import ElementTree

from fattern.engine import EngineMessage, LayoutResult

SVG_NS = "http://www.w3.org/2000/svg"
ElementTree.register_namespace("", SVG_NS)


def render_marker_svg(result: LayoutResult, title: str = "Marker layout") -> str:
    """Render a marker SVG from an already computed LayoutResult.

    The renderer does not calculate layout values. It only serializes
    fabric_width, marker_length, messages, and placements from the result.
    """

    viewbox_width = _positive_viewbox_dimension(result.fabric_width)
    viewbox_height = _positive_viewbox_dimension(result.marker_length)
    warning_codes = _warning_codes(result.messages)

    root_attrs = {
        "xmlns": SVG_NS,
        "viewBox": f"0 0 {_fmt(viewbox_width)} {_fmt(viewbox_height)}",
        "preserveAspectRatio": "xMidYMid meet",
        "role": "img",
        "data-unit": result.unit,
    }
    if warning_codes:
        root_attrs["data-warning"] = " ".join(warning_codes)

    svg = ElementTree.Element("svg", root_attrs)
    title_el = ElementTree.SubElement(svg, "title")
    title_el.text = title

    if warning_codes:
        desc = ElementTree.SubElement(svg, "desc")
        desc.text = "; ".join(message.message for message in result.messages if message.severity == "warning")

    ElementTree.SubElement(
        svg,
        "rect",
        {
            "class": "fabric-boundary",
            "x": "0",
            "y": "0",
            "width": _fmt(result.fabric_width),
            "height": _fmt(result.marker_length),
            "fill": "none",
            "stroke": "#1f2937",
            "stroke-width": _stroke_width(result),
        },
    )

    for placement in result.placements:
        group = ElementTree.SubElement(
            svg,
            "g",
            {
                "class": "piece",
                "data-piece-id": placement.piece_id,
                "data-layer": placement.layer,
                "data-rotation": str(placement.rotation_degrees),
                "transform": f"translate({_fmt(placement.x)} {_fmt(placement.y)})",
            },
        )
        ElementTree.SubElement(
            group,
            "rect",
            {
                "class": "piece-shape",
                "x": "0",
                "y": "0",
                "width": _fmt(placement.width),
                "height": _fmt(placement.height),
                "fill": "#dbeafe",
                "stroke": "#2563eb",
                "stroke-width": _stroke_width(result),
            },
        )
        label = ElementTree.SubElement(
            group,
            "text",
            {
                "class": "piece-label",
                "x": _fmt(placement.width / 2.0),
                "y": _fmt(placement.height / 2.0),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-size": _label_size(result),
                "fill": "#111827",
            },
        )
        label.text = placement.piece_id

    return ElementTree.tostring(svg, encoding="unicode", short_empty_elements=True)


def _warning_codes(messages: Sequence[EngineMessage]) -> tuple[str, ...]:
    return tuple(message.code for message in messages if message.severity == "warning")


def _positive_viewbox_dimension(value: float) -> float:
    return value if value > 0 else 1.0


def _stroke_width(result: LayoutResult) -> str:
    dimension = min(_positive_viewbox_dimension(result.fabric_width), _positive_viewbox_dimension(result.marker_length))
    return _fmt(max(dimension / 400.0, 0.02))


def _label_size(result: LayoutResult) -> str:
    dimension = min(_positive_viewbox_dimension(result.fabric_width), _positive_viewbox_dimension(result.marker_length))
    return _fmt(max(dimension / 35.0, 0.2))


def _fmt(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"
