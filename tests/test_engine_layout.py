import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.engine import (
    EngineMessage,
    LayoutPlacement,
    MetricsResult,
    estimate_marker_layout,
    validate_marker_layout,
)
import fattern.engine.layout as layout_module
from fattern.engine.models import PieceMetrics
from fattern.geometry import BoundingBox, bounding_box, polygon_area, polygon_perimeter


def metric(piece_id: str, width: float, height: float, unit: str = "cm") -> PieceMetrics:
    return PieceMetrics(
        piece_id=piece_id,
        layer="OUTLINE",
        bbox=BoundingBox(0.0, 0.0, width, height),
        area=width * height,
        perimeter=2.0 * (width + height),
        unit=unit,
        point_count=4,
    )


def polygon_metric(piece_id: str, points: tuple[tuple[float, float], ...], unit: str = "cm") -> PieceMetrics:
    return PieceMetrics(
        piece_id=piece_id,
        layer="OUTLINE",
        bbox=bounding_box(points),
        area=polygon_area(points),
        perimeter=polygon_perimeter(points),
        unit=unit,
        point_count=len(points),
        points=points,
    )


class LayoutTests(unittest.TestCase):
    def test_two_pieces_fit_within_fabric_width(self) -> None:
        metrics = MetricsResult(
            metrics=(metric("piece_0001", 4.0, 3.0), metric("piece_0002", 2.0, 2.0)),
            messages=(),
        )

        result = estimate_marker_layout(metrics, fabric_width=6.2)

        self.assertFalse(result.has_blocker())
        self.assertTrue(result.validity.within_fabric_width)
        self.assertTrue(result.validity.no_overlap)
        self.assertEqual(result.no_overlap, True)
        self.assertEqual(len(result.placements), 2)
        self.assertAlmostEqual(result.placements[0].x, 0.0)
        self.assertAlmostEqual(result.placements[1].x, 4.2)
        self.assertAlmostEqual(result.marker_length, 3.0)
        self.assertAlmostEqual(result.efficiency, 16.0 / (6.2 * 3.0))

    def test_fabric_width_overflow_moves_to_next_row_with_clearance(self) -> None:
        metrics = MetricsResult(
            metrics=(metric("piece_0001", 4.0, 3.0), metric("piece_0002", 2.0, 2.0)),
            messages=(),
        )

        result = estimate_marker_layout(metrics, fabric_width=6.1)

        self.assertFalse(result.has_blocker())
        self.assertTrue(result.validity.within_fabric_width)
        self.assertTrue(result.validity.no_overlap)
        self.assertAlmostEqual(result.placements[1].x, 0.0)
        self.assertAlmostEqual(result.placements[1].y, 3.2)
        self.assertAlmostEqual(result.marker_length, 5.2)

    def test_compact_layout_reuses_gap_above_short_piece(self) -> None:
        metrics = MetricsResult(
            metrics=(
                metric("piece_0001", 7.0, 5.0),
                metric("piece_0002", 3.0, 2.0),
                metric("piece_0003", 3.0, 2.0),
            ),
            messages=(),
        )

        result = estimate_marker_layout(metrics, fabric_width=10.2)

        self.assertFalse(result.has_blocker())
        self.assertAlmostEqual(result.marker_length, 5.0)
        self.assertAlmostEqual(result.placements[2].x, 7.2)
        self.assertAlmostEqual(result.placements[2].y, 2.2)

    def test_compact_layout_tries_larger_piece_order_to_reduce_length(self) -> None:
        metrics = MetricsResult(
            metrics=(
                metric("piece_0001", 3.0, 2.0),
                metric("piece_0002", 3.0, 2.0),
                metric("piece_0003", 7.0, 5.0),
            ),
            messages=(),
        )

        result = estimate_marker_layout(metrics, fabric_width=10.2)

        self.assertFalse(result.has_blocker())
        self.assertAlmostEqual(result.marker_length, 5.0)
        self.assertEqual(result.placements[0].piece_id, "piece_0003")
        self.assertAlmostEqual(result.placements[1].x, 7.2)
        self.assertAlmostEqual(result.placements[1].y, 0.0)
        self.assertAlmostEqual(result.placements[2].x, 7.2)
        self.assertAlmostEqual(result.placements[2].y, 2.2)

    def test_complex_polygon_layout_still_tries_height_order(self) -> None:
        original_threshold = layout_module.COMPLEX_OUTLINE_POINT_THRESHOLD
        layout_module.COMPLEX_OUTLINE_POINT_THRESHOLD = 1
        try:
            metrics = MetricsResult(
                metrics=(
                    polygon_metric("piece_0001", ((0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0))),
                    polygon_metric("piece_0002", ((0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0))),
                    polygon_metric("piece_0003", ((0.0, 0.0), (7.0, 0.0), (7.0, 5.0), (0.0, 5.0))),
                ),
                messages=(),
            )

            result = estimate_marker_layout(metrics, fabric_width=10.2)
        finally:
            layout_module.COMPLEX_OUTLINE_POINT_THRESHOLD = original_threshold

        self.assertFalse(result.has_blocker())
        self.assertAlmostEqual(result.marker_length, 5.0)
        self.assertEqual(result.placements[0].piece_id, "piece_0003")
        self.assertFalse(any(message.code == "BBOX_FALLBACK_USED" for message in result.messages))

    def test_longest_edge_order_uses_piece_id_tiebreaker(self) -> None:
        metrics = (metric("piece_b", 3.0, 4.0), metric("piece_a", 4.0, 3.0))

        orders = layout_module._metric_orders(metrics)

        self.assertIn(("piece_a", "piece_b"), [tuple(item.piece_id for item in order) for order in orders])

    def test_longest_edge_down_rotation_attempt_prefers_vertical_major_edge(self) -> None:
        wide = metric("wide", 8.0, 2.0)

        normal_rank = layout_module._rotation_rank(wide, 0, 0, (0, 90), True)
        rotated_rank = layout_module._rotation_rank(wide, 90, 1, (0, 90), True)

        self.assertLess(rotated_rank, normal_rank)

    def test_compact_within_shelf_reuses_space_above_next_row(self) -> None:
        placements = (
            LayoutPlacement("tall", "OUTLINE", 0.0, 0.0, 5.0, 5.0, 0),
            LayoutPlacement("short", "OUTLINE", 5.2, 0.0, 2.0, 2.0, 0),
            LayoutPlacement("next", "OUTLINE", 5.2, 5.2, 2.0, 2.0, 0),
        )

        compacted = layout_module._compact_within_shelf(placements, fabric_width=7.2, clearance=0.2)

        moved = next(placement for placement in compacted if placement.piece_id == "next")
        self.assertAlmostEqual(moved.x, 5.2)
        self.assertAlmostEqual(moved.y, 2.2)

    def test_polygon_layout_nests_inside_concave_gap(self) -> None:
        metrics = MetricsResult(
            metrics=(
                polygon_metric(
                    "piece_0001",
                    ((0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (1.0, 1.0), (1.0, 4.0), (0.0, 4.0)),
                ),
                polygon_metric("piece_0002", ((0.0, 0.0), (2.6, 0.0), (2.6, 2.6), (0.0, 2.6))),
            ),
            messages=(),
        )

        result = estimate_marker_layout(metrics, fabric_width=4.0)

        self.assertFalse(result.has_blocker())
        self.assertTrue(result.validity.no_overlap)
        self.assertAlmostEqual(result.marker_length, 4.0)
        self.assertAlmostEqual(result.placements[1].x, 1.4)
        self.assertAlmostEqual(result.placements[1].y, 0.0)
        self.assertTrue(result.placements[0].outline_points)

    def test_rotation_rule_is_respected(self) -> None:
        metrics = MetricsResult(metrics=(metric("piece_0001", 7.0, 3.0),), messages=())

        blocked = estimate_marker_layout(metrics, fabric_width=5.0, rotation_allowed_degrees=(0, 180))
        rotated = estimate_marker_layout(metrics, fabric_width=5.0, rotation_allowed_degrees=(90,))

        self.assertTrue(blocked.has_blocker())
        self.assertEqual(blocked.messages[0].code, "FABRIC_WIDTH_EXCEEDED")
        self.assertFalse(blocked.validity.within_fabric_width)
        self.assertFalse(rotated.has_blocker())
        self.assertEqual(rotated.placements[0].rotation_degrees, 90)
        self.assertAlmostEqual(rotated.placements[0].width, 3.0)
        self.assertAlmostEqual(rotated.placements[0].height, 7.0)

    def test_spacing_is_applied_as_minimum_piece_gap(self) -> None:
        metrics = MetricsResult(
            metrics=(metric("piece_0001", 4.0, 3.0), metric("piece_0002", 2.0, 2.0)),
            messages=(),
        )

        result = estimate_marker_layout(metrics, fabric_width=6.1, clearance=0.2, spacing=0.0)

        self.assertFalse(result.has_blocker())
        self.assertAlmostEqual(result.placements[1].x, 4.0)
        self.assertAlmostEqual(result.placements[1].y, 0.0)
        self.assertTrue(any(message.code == "SPACING_OVERRIDES_CLEARANCE" for message in result.messages))

    def test_cuttable_width_is_prioritized_for_layout_width(self) -> None:
        metrics = MetricsResult(
            metrics=(metric("piece_0001", 4.0, 3.0), metric("piece_0002", 2.0, 2.0)),
            messages=(),
        )

        result = estimate_marker_layout(metrics, fabric_width=6.2, cuttable_width=6.1)

        self.assertFalse(result.has_blocker())
        self.assertAlmostEqual(result.fabric_width, 6.1)
        self.assertAlmostEqual(result.marker_length, 5.2)
        self.assertTrue(any(message.code == "CUTTABLE_WIDTH_APPLIED" for message in result.messages))

    def test_cuttable_width_larger_than_fabric_width_returns_blocker(self) -> None:
        metrics = MetricsResult(metrics=(metric("piece_0001", 4.0, 3.0),), messages=())

        result = estimate_marker_layout(metrics, fabric_width=6.2, cuttable_width=6.3)

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.placements, ())
        self.assertAlmostEqual(result.fabric_width, 6.2)
        self.assertEqual(result.messages[0].code, "INVALID_CUTTABLE_WIDTH")

    def test_grainline_required_blocks_missing_grainline_without_nap_direction(self) -> None:
        metrics = MetricsResult(metrics=(metric("piece_0001", 4.0, 3.0),), messages=())

        result = estimate_marker_layout(
            metrics,
            fabric_width=10.0,
            grainline_status="missing",
            grainline_required=True,
        )

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.placements, ())
        self.assertEqual(result.messages[0].code, "MISSING_GRAINLINE_REQUIRED")

    def test_woven_fabric_blocks_missing_grainline_without_nap_direction(self) -> None:
        metrics = MetricsResult(metrics=(metric("piece_0001", 4.0, 3.0),), messages=())

        result = estimate_marker_layout(
            metrics,
            fabric_width=10.0,
            grainline_status="missing",
            fabric_type="woven",
        )

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.placements, ())
        self.assertEqual(result.messages[0].code, "MISSING_GRAINLINE_FOR_WOVEN")

    def test_nap_direction_one_way_filters_180_without_grainline_blocker(self) -> None:
        metrics = MetricsResult(metrics=(metric("piece_0001", 4.0, 3.0),), messages=())

        result = estimate_marker_layout(
            metrics,
            fabric_width=10.0,
            rotation_allowed_degrees=(0, 180),
            nap_direction="one_way",
            grainline_status="missing",
        )

        self.assertFalse(result.has_blocker())
        self.assertEqual(result.rotation_allowed_degrees, (0,))
        self.assertEqual(result.placements[0].rotation_degrees, 0)
        self.assertTrue(
            any(message.code == "NAP_DIRECTION_ONE_WAY_BLOCKED_180_ROTATION" for message in result.messages)
        )
        self.assertFalse(any(message.code.startswith("MISSING_GRAINLINE") for message in result.messages))

    def test_one_way_fabric_requires_grainline_presence(self) -> None:
        metrics = MetricsResult(metrics=(metric("piece_0001", 4.0, 3.0),), messages=())

        result = estimate_marker_layout(
            metrics,
            fabric_width=10.0,
            one_way_fabric=True,
            grainline_status="missing",
        )

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.messages[0].code, "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC")
        self.assertEqual(result.placements, ())

    def test_unsupported_nap_direction_returns_blocker(self) -> None:
        metrics = MetricsResult(metrics=(metric("piece_0001", 4.0, 3.0),), messages=())

        result = estimate_marker_layout(metrics, fabric_width=10.0, nap_direction="directional")

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.messages[0].code, "UNSUPPORTED_NAP_DIRECTION")

    def test_overlap_validation_returns_overlap_detected(self) -> None:
        placements = (
            LayoutPlacement("piece_0001", "OUTLINE", 0.0, 0.0, 3.0, 2.0, 0),
            LayoutPlacement("piece_0002", "OUTLINE", 2.9, 0.0, 3.0, 2.0, 0),
        )

        validity, messages = validate_marker_layout(placements, fabric_width=10.0)

        self.assertFalse(validity.no_overlap)
        self.assertEqual(messages[0].code, "OVERLAP_DETECTED")

    def test_overlap_validation_reuses_absolute_outline_cache(self) -> None:
        outline = ((0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0))
        placements = (
            LayoutPlacement("piece_0001", "OUTLINE", 0.0, 0.0, 3.0, 2.0, 0, outline_points=outline),
            LayoutPlacement("piece_0002", "OUTLINE", 1.0, 0.0, 3.0, 2.0, 0, outline_points=outline),
            LayoutPlacement("piece_0003", "OUTLINE", 2.0, 0.0, 3.0, 2.0, 0, outline_points=outline),
        )
        original = layout_module._absolute_outline_points
        calls: list[str] = []

        def counting_absolute_points(placement: LayoutPlacement) -> tuple[tuple[float, float], ...]:
            calls.append(placement.piece_id)
            return original(placement)

        layout_module._absolute_outline_points = counting_absolute_points
        try:
            validity, messages = validate_marker_layout(placements, fabric_width=10.0)
        finally:
            layout_module._absolute_outline_points = original

        self.assertFalse(validity.no_overlap)
        self.assertEqual(messages[0].code, "OVERLAP_DETECTED")
        self.assertLessEqual(len(calls), len(placements))

    def test_fabric_width_validation_returns_width_error(self) -> None:
        placements = (LayoutPlacement("piece_0001", "OUTLINE", 1.0, 0.0, 5.0, 2.0, 0),)

        validity, messages = validate_marker_layout(placements, fabric_width=5.0)

        self.assertFalse(validity.within_fabric_width)
        self.assertEqual(messages[0].code, "FABRIC_WIDTH_EXCEEDED")

    def test_metrics_blocker_stops_layout(self) -> None:
        metrics = MetricsResult(
            metrics=(metric("piece_0001", 4.0, 3.0),),
            messages=(EngineMessage(code="SELF_INTERSECTION", message="bad piece", severity="blocker"),),
        )

        result = estimate_marker_layout(metrics, fabric_width=10.0)

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.placements, ())
        self.assertEqual(result.messages[0].code, "SELF_INTERSECTION")
        self.assertAlmostEqual(result.marker_length, 0.0)


if __name__ == "__main__":
    unittest.main()
