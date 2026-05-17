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

    fabric_viewbox_width = _positive_viewbox_dimension(result.fabric_width)
    viewbox_height = _positive_viewbox_dimension(result.marker_length)
    info_gap = _info_gap(result)
    info_width = _info_panel_width(result)
    viewbox_width = fabric_viewbox_width + info_gap + info_width
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
        if placement.outline_points:
            ElementTree.SubElement(
                group,
                "polygon",
                {
                    "class": "piece-shape",
                    "points": _points(placement.outline_points),
                    "fill": "#dbeafe",
                    "stroke": "#2563eb",
                    "stroke-width": _stroke_width(result),
                },
            )
        else:
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

    _append_info_panel(svg, result, x=result.fabric_width + info_gap, width=info_width)

    return ElementTree.tostring(svg, encoding="unicode", short_empty_elements=True)


def _warning_codes(messages: Sequence[EngineMessage]) -> tuple[str, ...]:
    return tuple(message.code for message in messages if message.severity == "warning")


def _positive_viewbox_dimension(value: float) -> float:
    return value if value > 0 else 1.0


def _stroke_width(result: LayoutResult) -> str:
    dimension = min(_positive_viewbox_dimension(result.fabric_width), _positive_viewbox_dimension(result.marker_length))
    return _fmt(max(dimension / 400.0, 0.02))


def _label_size(result: LayoutResult) -> str:
    return _fmt(_label_size_value(result))


def _label_size_value(result: LayoutResult) -> float:
    dimension = min(_positive_viewbox_dimension(result.fabric_width), _positive_viewbox_dimension(result.marker_length))
    return max(dimension / 35.0, 0.2)


def _info_gap(result: LayoutResult) -> float:
    dimension = min(_positive_viewbox_dimension(result.fabric_width), _positive_viewbox_dimension(result.marker_length))
    return max(dimension / 24.0, 0.25)


def _info_panel_width(result: LayoutResult) -> float:
    dimension = min(_positive_viewbox_dimension(result.fabric_width), _positive_viewbox_dimension(result.marker_length))
    proportional_width = min(result.fabric_width * 0.4, dimension * 2.0)
    text_floor = min(dimension * 1.2, 8.0)
    return max(proportional_width, text_floor, 3.0)


def _append_info_panel(svg: ElementTree.Element, result: LayoutResult, *, x: float, width: float) -> None:
    font_size = _label_size_value(result)
    line_gap = font_size * 1.45
    panel = ElementTree.SubElement(
        svg,
        "g",
        {
            "class": "marker-info",
            "transform": f"translate({_fmt(x)} 0)",
        },
    )
    ElementTree.SubElement(
        panel,
        "rect",
        {
            "class": "marker-info-background",
            "x": "0",
            "y": "0",
            "width": _fmt(width),
            "height": _fmt(result.marker_length),
            "fill": "#f8fafc",
            "stroke": "#94a3b8",
            "stroke-width": _stroke_width(result),
        },
    )
    text_rows = (
        f"fabric width: {_fmt(result.fabric_width)} {result.unit}",
        f"marker length: {_fmt(result.marker_length)} {result.unit}",
        f"grainline: {result.grainline_status}",
        f"rotation: {','.join(str(value) for value in result.rotation_allowed_degrees)} deg",
    )
    y = line_gap
    for row in text_rows:
        text = ElementTree.SubElement(
            panel,
            "text",
            {
                "class": "marker-info-label",
                "x": _fmt(font_size),
                "y": _fmt(y),
                "font-size": _fmt(font_size),
                "fill": "#0f172a",
            },
        )
        text.text = row
        y += line_gap

    arrow_x = font_size * 1.2
    arrow_top = max(y, font_size * 6.0)
    arrow_bottom = max(result.marker_length - font_size * 1.8, arrow_top + font_size)
    ElementTree.SubElement(
        panel,
        "line",
        {
            "class": "grainline-direction",
            "x1": _fmt(arrow_x),
            "y1": _fmt(arrow_top),
            "x2": _fmt(arrow_x),
            "y2": _fmt(arrow_bottom),
            "stroke": "#475569",
            "stroke-width": _stroke_width(result),
        },
    )
    ElementTree.SubElement(
        panel,
        "polygon",
        {
            "class": "grainline-arrow",
            "points": _points(
                (
                    (arrow_x, arrow_bottom),
                    (arrow_x - font_size * 0.45, arrow_bottom - font_size * 0.9),
                    (arrow_x + font_size * 0.45, arrow_bottom - font_size * 0.9),
                )
            ),
            "fill": "#475569",
        },
    )


def _fmt(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _points(points: Sequence[tuple[float, float]]) -> str:
    return " ".join(f"{_fmt(point[0])},{_fmt(point[1])}" for point in points)
