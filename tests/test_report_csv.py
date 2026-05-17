import csv
import sys
import unittest
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.engine import LayoutPlacement, LayoutResult, PieceMetrics
from fattern.geometry import BoundingBox
from fattern.report import PieceReportMetadata, partial_csv_fields, render_marker_csv


def layout_result() -> LayoutResult:
    return LayoutResult(
        placements=(
            LayoutPlacement(
                piece_id='front,"main"',
                layer="OUTLINE",
                x=1.5,
                y=2.25,
                width=4.0,
                height=5.0,
                rotation_degrees=90,
            ),
            LayoutPlacement(
                piece_id="back_panel",
                layer="OUTLINE",
                x=8.0,
                y=0.0,
                width=2.0,
                height=3.0,
                rotation_degrees=0,
            ),
        ),
        fabric_width=20.0,
        marker_length=30.0,
        efficiency=0.5,
        clearance=0.2,
        unit="mm",
        no_overlap=True,
        messages=(),
        within_fabric_width=True,
        total_piece_area=26.0,
        rotation_allowed_degrees=(0, 90),
    )


class CsvReportTests(unittest.TestCase):
    def test_csv_uses_standard_writer_and_preserves_output_numbers(self) -> None:
        csv_text = render_marker_csv(
            layout_result(),
            piece_metrics={
                'front,"main"': PieceMetrics(
                    piece_id='front,"main"',
                    layer="OUTLINE",
                    bbox=BoundingBox(min_x=0.0, min_y=0.0, max_x=4.0, max_y=5.0),
                    area=20.0,
                    perimeter=18.0,
                    unit="mm",
                    point_count=4,
                ),
            },
            piece_metadata={
                'front,"main"': PieceReportMetadata(
                    piece_name='front,"main"',
                    size="L",
                    quantity=2,
                    grainline_status="parallel",
                ),
            },
        )
        rows = list(csv.DictReader(StringIO(csv_text)))

        self.assertEqual(
            rows[0],
            {
                "piece_id": 'front,"main"',
                "piece_name": 'front,"main"',
                "size": "L",
                "quantity": "2",
                "area_mm2": "20",
                "bbox_width_mm": "4",
                "bbox_height_mm": "5",
                "x_mm": "1.5",
                "y_mm": "2.25",
                "rotation": "90",
                "grainline_status": "parallel",
            },
        )
        self.assertIn('"front,""main"""', csv_text)

    def test_missing_fields_stay_empty_without_invented_values(self) -> None:
        csv_text = render_marker_csv(layout_result())
        rows = list(csv.DictReader(StringIO(csv_text)))

        self.assertEqual(rows[1]["piece_name"], "")
        self.assertEqual(rows[1]["size"], "")
        self.assertEqual(rows[1]["quantity"], "")
        self.assertEqual(rows[1]["area_mm2"], "")
        self.assertEqual(rows[1]["bbox_width_mm"], "")
        self.assertEqual(rows[1]["bbox_height_mm"], "")
        self.assertEqual(rows[1]["grainline_status"], "")
        self.assertEqual(rows[1]["x_mm"], "8")
        self.assertEqual(rows[1]["rotation"], "0")

    def test_partial_csv_fields_are_documented(self) -> None:
        self.assertEqual(
            tuple(partial_csv_fields()),
            (
                "piece_name",
                "size",
                "quantity",
                "grainline_status",
            ),
        )


if __name__ == "__main__":
    unittest.main()
