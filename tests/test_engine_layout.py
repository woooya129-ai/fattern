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
from fattern.engine.models import PieceMetrics
from fattern.geometry import BoundingBox


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

    def test_compact_layout_keeps_stacked_alternative_to_reduce_length(self) -> None:
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
        self.assertEqual(result.placements[0].piece_id, "piece_0001")
        self.assertAlmostEqual(result.placements[1].x, 0.0)
        self.assertAlmostEqual(result.placements[1].y, 2.2)
        self.assertAlmostEqual(result.placements[2].x, 3.2)
        self.assertAlmostEqual(result.placements[2].y, 0.0)

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

    def test_overlap_validation_returns_overlap_detected(self) -> None:
        placements = (
            LayoutPlacement("piece_0001", "OUTLINE", 0.0, 0.0, 3.0, 2.0, 0),
            LayoutPlacement("piece_0002", "OUTLINE", 2.9, 0.0, 3.0, 2.0, 0),
        )

        validity, messages = validate_marker_layout(placements, fabric_width=10.0)

        self.assertFalse(validity.no_overlap)
        self.assertEqual(messages[0].code, "OVERLAP_DETECTED")

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
