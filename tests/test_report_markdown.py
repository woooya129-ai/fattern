import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.engine import EngineMessage, ExcludedCandidate, LayoutPlacement, LayoutResult
from fattern.report import render_marker_report
from fattern.report.markdown import ExcludedPiece


def layout_result() -> LayoutResult:
    return LayoutResult(
        placements=(
            LayoutPlacement(
                piece_id="front|panel<1>",
                layer="OUTLINE`main`",
                x=1.0,
                y=2.0,
                width=3.0,
                height=4.0,
                rotation_degrees=90,
            ),
        ),
        fabric_width=10.0,
        marker_length=20.0,
        efficiency=0.25,
        clearance=0.2,
        unit="cm",
        no_overlap=True,
        messages=(
            EngineMessage(code="SMALL_GAP", message="gap | check <safe>", severity="warning"),
        ),
        within_fabric_width=True,
        total_piece_area=50.0,
        rotation_allowed_degrees=(0, 90),
    )


class MarkdownReportTests(unittest.TestCase):
    def test_report_uses_layout_result_numbers(self) -> None:
        report = render_marker_report(layout_result())

        self.assertIn("- fabric_width: 10 cm", report)
        self.assertIn("- marker_length: 20 cm", report)
        self.assertIn("- efficiency: 0.25", report)
        self.assertIn("- total_piece_area: 50 cm^2", report)
        self.assertIn("| front\\|panel&lt;1&gt; | OUTLINE\\`main\\` | 1 | 2 | 3 | 4 | 90 |", report)

    def test_warnings_and_excluded_pieces_are_escaped(self) -> None:
        report = render_marker_report(
            layout_result(),
            excluded_pieces=(
                ExcludedPiece(piece_id="bad|piece", layer="L<1>", reason_code="OPEN`POLY", message="open | line"),
                ExcludedCandidate(
                    entity_type="LINE",
                    layer="raw|layer",
                    reason_code="UNSUPPORTED_ENTITY",
                    message="ignored <LINE>",
                    source_entity_index=7,
                ),
            ),
        )

        self.assertIn("- `SMALL_GAP` gap \\| check &lt;safe&gt;", report)
        self.assertIn("| bad\\|piece | L&lt;1&gt; | `OPENPOLY` | open \\| line |", report)
        self.assertIn("| entity\\_0007 | raw\\|layer | `UNSUPPORTED_ENTITY` | ignored &lt;LINE&gt; |", report)

    def test_empty_sections_are_explicit(self) -> None:
        empty = LayoutResult(
            placements=(),
            fabric_width=1.0,
            marker_length=0.0,
            efficiency=0.0,
            clearance=0.2,
            unit="cm",
            no_overlap=True,
            messages=(),
        )

        report = render_marker_report(empty)

        self.assertIn("## Placements\n\n- none", report)
        self.assertIn("## Warnings\n\n- none", report)
        self.assertIn("## Excluded Pieces\n\n- none", report)


if __name__ == "__main__":
    unittest.main()
