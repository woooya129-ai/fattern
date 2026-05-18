import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.jobs import JobStore
from fattern.web import estimate_upload, parse_multipart_form


FIXTURE_DIR = ROOT / "tests" / "fixtures"


class WebUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fattern-web-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_estimate_upload_uses_file_bytes_and_returns_artifact_links(self) -> None:
        store = JobStore(self.temp_dir / "jobs")
        result = estimate_upload(
            file_name="sample.dxf",
            file_bytes=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
            fields={
                "fabric_width": "10",
                "unit": "cm",
                "spacing": "0.2",
                "seam_allowance_status": "included",
                "nap_direction": "two_way",
                "grainline_required": "false",
                "allowed_rotation": "0",
                "allowance_policy_mode": "fast_quote",
                "fabric_type": "unknown",
                "shrinkage_percent": "0",
            },
            store=store,
            output_root=self.temp_dir / "output",
            web_base_url="http://127.0.0.1:8765",
        )

        self.assertEqual(result.result["status"], "completed")
        self.assertEqual(result.result["layout"]["marker_length"], 3.0)
        self.assertEqual(result.result["minimum_yield"]["marker_length"], 3.0)
        self.assertIn("quote_yield", result.result)
        self.assertIsNotNone(result.archive_artifact_id)
        self.assertIsNotNone(result.run)
        assert result.run is not None
        self.assertTrue((result.run.output_dir / "marker_preview.svg").is_file())
        self.assertTrue((result.run.output_dir / "result.json").is_file())
        self.assertTrue((result.run.output_dir / "run_summary.txt").is_file())
        self.assertIn("web_url", result.result)

    def test_parse_multipart_form_extracts_fields_and_file(self) -> None:
        boundary = "----fattern-test"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="fabric_width"\r\n\r\n'
            "150\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="dxf_file"; filename="sample.dxf"\r\n'
            "Content-Type: application/dxf\r\n\r\n"
            "0\nEOF\n\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        fields, files = parse_multipart_form(f"multipart/form-data; boundary={boundary}", body)

        self.assertEqual(fields["fabric_width"], "150")
        self.assertEqual(files["dxf_file"], ("sample.dxf", b"0\nEOF\n"))


if __name__ == "__main__":
    unittest.main()
