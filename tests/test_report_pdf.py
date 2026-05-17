import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.report import render_marker_pdf


class PdfReportTests(unittest.TestCase):
    def test_pdf_report_has_valid_header_and_escaped_text_stream(self) -> None:
        pdf = render_marker_pdf("# Marker Report\n\n- marker_length: 3 cm\n- note: (safe) \\ path")

        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"/Type /Catalog", pdf)
        self.assertIn(b"marker_length: 3 cm", pdf)
        self.assertIn(b"\\(safe\\) \\\\ path", pdf)
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))


if __name__ == "__main__":
    unittest.main()
