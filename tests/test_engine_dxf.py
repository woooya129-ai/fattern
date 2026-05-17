import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.engine import parse_dxf_file, parse_dxf_text


FIXTURE_DIR = ROOT / "tests" / "fixtures"


class DxfParserTests(unittest.TestCase):
    def test_empty_file_returns_parse_failed_blocker(self) -> None:
        result = parse_dxf_text("")

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.messages[0].code, "PARSE_FAILED")
        self.assertEqual(result.messages[0].severity, "blocker")

    def test_malformed_dxf_returns_parse_failed_blocker(self) -> None:
        result = parse_dxf_text("0\nSECTION\n2\nENTITIES\n0\nLWPOLYLINE\n10")

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.messages[0].code, "PARSE_FAILED")

    def test_unsupported_version_returns_blocker(self) -> None:
        result = parse_dxf_file(FIXTURE_DIR / "unsupported_version.dxf")

        self.assertTrue(result.has_blocker())
        self.assertEqual(result.messages[0].code, "UNSUPPORTED_DXF_VERSION")
        self.assertEqual(result.acad_version, "AC1006")

    def test_lwpolyline_rectangle_returns_closed_candidate(self) -> None:
        result = parse_dxf_file(FIXTURE_DIR / "rectangle_lwpolyline.dxf")

        self.assertFalse(result.has_blocker())
        self.assertEqual(result.summary.total_entities, 1)
        self.assertEqual(result.summary.counts_by_type["LWPOLYLINE"], 1)
        self.assertEqual(result.summary.closed_lwpolyline_count, 1)
        self.assertEqual(len(result.piece_candidates), 1)
        candidate = result.piece_candidates[0]
        self.assertEqual(candidate.piece_id, "piece_0001")
        self.assertEqual(candidate.layer, "OUTLINE")
        self.assertTrue(candidate.closed)
        self.assertEqual(candidate.points, ((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)))

    def test_r12_polyline_rectangle_returns_closed_candidate(self) -> None:
        result = parse_dxf_file(FIXTURE_DIR / "rectangle_polyline_r12.dxf")

        self.assertFalse(result.has_blocker())
        self.assertEqual(result.acad_version, "AC1009")
        self.assertEqual(result.summary.total_entities, 1)
        self.assertEqual(result.summary.counts_by_type["POLYLINE"], 1)
        self.assertEqual(result.summary.polyline_count, 1)
        self.assertEqual(result.summary.closed_polyline_count, 1)
        self.assertEqual(len(result.piece_candidates), 1)
        candidate = result.piece_candidates[0]
        self.assertEqual(candidate.piece_id, "piece_0001")
        self.assertEqual(candidate.layer, "OUTLINE")
        self.assertTrue(candidate.closed)
        self.assertEqual(candidate.points, ((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)))

    def test_non_closed_lwpolyline_is_excluded(self) -> None:
        result = parse_dxf_file(FIXTURE_DIR / "open_lwpolyline.dxf")

        self.assertFalse(result.has_blocker())
        self.assertEqual(result.summary.open_lwpolyline_count, 1)
        self.assertEqual(result.piece_candidates, ())
        self.assertEqual(len(result.excluded_candidates), 1)
        self.assertEqual(result.excluded_candidates[0].reason_code, "NON_CLOSED_CONTOUR")
        self.assertEqual(result.messages[0].code, "NON_CLOSED_CONTOUR")
        self.assertEqual(result.messages[0].severity, "warning")

    def test_semantic_line_and_text_entities_are_separated_from_piece_geometry(self) -> None:
        result = parse_dxf_text(_semantic_dxf())

        self.assertFalse(result.has_blocker())
        self.assertEqual(result.summary.counts_by_type["LWPOLYLINE"], 1)
        self.assertEqual(result.summary.counts_by_type["LINE"], 1)
        self.assertEqual(result.summary.counts_by_type["TEXT"], 1)
        self.assertEqual(result.piece_candidates[0].piece_name, "Front")
        self.assertEqual(result.piece_candidates[0].size, "M")
        self.assertEqual(result.line_entities[0].layer, "GRAINLINE")
        self.assertEqual(result.text_entities[0].text, "Front label")
        self.assertEqual(result.excluded_candidates[0].reason_code, "ANNOTATION_TEXT_IGNORED")
        self.assertIn("ANNOTATION_TEXT_UNTRUSTED", [message.code for message in result.messages])


def _semantic_dxf() -> str:
    return "\n".join(
        [
            "0", "SECTION",
            "2", "ENTITIES",
            "0", "LWPOLYLINE",
            "8", "piece=Front;size=M",
            "90", "4",
            "70", "1",
            "10", "0",
            "20", "0",
            "10", "4",
            "20", "0",
            "10", "4",
            "20", "3",
            "10", "0",
            "20", "3",
            "0", "LINE",
            "8", "GRAINLINE",
            "10", "2",
            "20", "0.5",
            "11", "2",
            "21", "2.5",
            "0", "TEXT",
            "8", "LABEL",
            "10", "1",
            "20", "1",
            "1", "Front label",
            "0", "ENDSEC",
            "0", "EOF",
        ]
    )


if __name__ == "__main__":
    unittest.main()
