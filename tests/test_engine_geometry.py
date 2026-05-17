import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.engine import PolylineCandidate, calculate_piece_metrics
from fattern.geometry import bounding_box, polygon_area, polygon_perimeter


def candidate(points: tuple[tuple[float, float], ...]) -> PolylineCandidate:
    return PolylineCandidate(
        piece_id="piece_0001",
        layer="OUTLINE",
        points=points,
        closed=True,
        source_entity_index=1,
        vertex_count=len(points),
    )


class GeometryMetricTests(unittest.TestCase):
    def test_rectangle_bbox_width_and_height(self) -> None:
        box = bounding_box(((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)))

        self.assertEqual(box.min_x, 0.0)
        self.assertEqual(box.min_y, 0.0)
        self.assertEqual(box.max_x, 4.0)
        self.assertEqual(box.max_y, 3.0)
        self.assertEqual(box.width, 4.0)
        self.assertEqual(box.height, 3.0)

    def test_rectangle_area_and_perimeter(self) -> None:
        points = ((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0))

        self.assertAlmostEqual(polygon_area(points), 12.0)
        self.assertAlmostEqual(polygon_perimeter(points), 14.0)

    def test_triangle_area(self) -> None:
        self.assertAlmostEqual(polygon_area(((0.0, 0.0), (4.0, 0.0), (0.0, 3.0))), 6.0)

    def test_piece_metrics_output(self) -> None:
        result = calculate_piece_metrics(candidate(((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0))))

        self.assertFalse(result.has_blocker())
        metric = result.metrics[0]
        self.assertEqual(metric.piece_id, "piece_0001")
        self.assertAlmostEqual(metric.bbox.width, 4.0)
        self.assertAlmostEqual(metric.bbox.height, 3.0)
        self.assertAlmostEqual(metric.area, 12.0)
        self.assertAlmostEqual(metric.perimeter, 14.0)
        self.assertEqual(metric.unit, "cm")

    def test_piece_metrics_apply_average_seam_allowance(self) -> None:
        result = calculate_piece_metrics(
            candidate(((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0))),
            seam_allowance_width=1.0,
        )

        self.assertFalse(result.has_blocker())
        metric = result.metrics[0]
        self.assertAlmostEqual(metric.bbox.width, 6.0)
        self.assertAlmostEqual(metric.bbox.height, 5.0)
        self.assertAlmostEqual(metric.area, 30.0)
        self.assertAlmostEqual(metric.perimeter, 22.0)
        self.assertAlmostEqual(metric.seam_allowance_width, 1.0)
        self.assertEqual(result.messages[0].code, "SEAM_ALLOWANCE_ESTIMATED")

    def test_self_intersection_returns_blocker(self) -> None:
        result = calculate_piece_metrics(candidate(((0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0))))

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.messages[0].code, "SELF_INTERSECTION")

    def test_zero_area_returns_invalid_polygon_blocker(self) -> None:
        result = calculate_piece_metrics(candidate(((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))))

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.messages[0].code, "INVALID_POLYGON")


if __name__ == "__main__":
    unittest.main()
