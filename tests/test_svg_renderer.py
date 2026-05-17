import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.engine import EngineMessage, LayoutPlacement, LayoutResult
from fattern.render import render_marker_svg


def layout_result() -> LayoutResult:
    return LayoutResult(
        placements=(
            LayoutPlacement(
                piece_id='front<panel>&"A"',
                layer="OUTLINE|main",
                x=0.0,
                y=0.0,
                width=4.0,
                height=3.0,
                rotation_degrees=0,
            ),
            LayoutPlacement(
                piece_id="back_panel",
                layer="OUTLINE",
                x=4.2,
                y=0.0,
                width=2.0,
                height=2.0,
                rotation_degrees=180,
            ),
        ),
        fabric_width=6.2,
        marker_length=3.0,
        efficiency=0.860215,
        clearance=0.2,
        unit="cm",
        no_overlap=True,
        messages=(
            EngineMessage(code="NARROW_CLEARANCE", message="clearance < preferred", severity="warning"),
        ),
        within_fabric_width=True,
        total_piece_area=16.0,
        rotation_allowed_degrees=(0, 180),
    )


class SvgRendererTests(unittest.TestCase):
    def test_renders_fabric_boundary_and_layout_placements(self) -> None:
        svg = render_marker_svg(layout_result())
        root = ElementTree.fromstring(svg)

        self.assertEqual(root.attrib["viewBox"], "0 0 6.2 3")
        self.assertEqual(root.attrib["preserveAspectRatio"], "xMidYMid meet")
        boundary = root.find(".//{http://www.w3.org/2000/svg}rect[@class='fabric-boundary']")
        self.assertIsNotNone(boundary)
        self.assertEqual(boundary.attrib["width"], "6.2")
        self.assertEqual(boundary.attrib["height"], "3")

        pieces = root.findall(".//{http://www.w3.org/2000/svg}g[@class='piece']")
        self.assertEqual(len(pieces), 2)
        self.assertEqual(pieces[0].attrib["transform"], "translate(0 0)")
        self.assertEqual(pieces[1].attrib["transform"], "translate(4.2 0)")
        self.assertEqual(pieces[1].attrib["data-rotation"], "180")

    def test_labels_and_attributes_are_escaped(self) -> None:
        svg = render_marker_svg(layout_result())

        self.assertIn("front&lt;panel&gt;&amp;&quot;A&quot;", svg)
        self.assertNotIn('data-piece-id="front<panel>', svg)
        root = ElementTree.fromstring(svg)
        label = root.find(".//{http://www.w3.org/2000/svg}text[@class='piece-label']")
        self.assertEqual(label.text, 'front<panel>&"A"')

    def test_warnings_are_exposed_as_safe_data_attribute(self) -> None:
        svg = render_marker_svg(layout_result())
        root = ElementTree.fromstring(svg)

        self.assertEqual(root.attrib["data-warning"], "NARROW_CLEARANCE")
        desc = root.find(".//{http://www.w3.org/2000/svg}desc")
        self.assertEqual(desc.text, "clearance < preferred")

    def test_svg_does_not_emit_active_or_external_resources(self) -> None:
        svg = render_marker_svg(layout_result())
        forbidden = ("<script", "<foreignObject", "href=", "xlink:href=", "<image", "url(")

        for token in forbidden:
            self.assertNotIn(token, svg)


if __name__ == "__main__":
    unittest.main()
