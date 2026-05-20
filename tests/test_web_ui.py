import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.jobs import JobStore
from fattern.web import _render_page, estimate_upload, parse_multipart_form


FIXTURE_DIR = ROOT / "tests" / "fixtures"


class WebUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fattern-web-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_render_page_includes_language_and_theme_toggles(self) -> None:
        html = _render_page()

        self.assertIn('data-lang="ko"', html)
        self.assertIn('data-lang="en"', html)
        self.assertIn('data-theme-choice="light"', html)
        self.assertIn('data-theme-choice="dark"', html)
        self.assertIn('data-ko="질문지"', html)
        self.assertIn('data-en="Questionnaire"', html)
        self.assertIn('fattern.language', html)
        self.assertIn('fattern.theme', html)

    def test_render_page_includes_unit_specific_dropdown_presets(self) -> None:
        html = _render_page()

        self.assertIn('data-unit-select', html)
        self.assertIn('data-unit-suffix', html)
        self.assertIn('data-preset-field', html)
        self.assertIn('data-preset-menu="fabric_width"', html)
        self.assertIn('data-preset-menu="cuttable_width"', html)
        self.assertIn('data-preset-menu="spacing"', html)
        self.assertIn('data-preset-menu="seam_allowance_width"', html)
        self.assertIn('inch: ["36", "44", "54", "56", "57", "58", "60"]', html)
        self.assertIn('fabric_width: { cm: "150", mm: "1500", m: "1.5", inch: "57"', html)
        self.assertIn('updateUnitControls', html)

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

    def test_estimate_upload_renders_seam_line_when_seam_allowance_excluded(self) -> None:
        store = JobStore(self.temp_dir / "jobs")
        result = estimate_upload(
            file_name="sample.dxf",
            file_bytes=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
            fields={
                "fabric_width": "10",
                "unit": "cm",
                "spacing": "0.2",
                "seam_allowance_status": "excluded",
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

        assert result.run is not None
        svg = (result.run.output_dir / "marker_preview.svg").read_text(encoding="utf-8")
        self.assertIn('class="seam-line"', svg)
        self.assertIn("SEAM_ALLOWANCE_DEFAULT_APPLIED", [warning["code"] for warning in result.result["warnings"]])

    def test_estimate_upload_rejects_fallback_width_when_seam_allowance_included(self) -> None:
        with self.assertRaisesRegex(ValueError, "Fallback width only applies"):
            estimate_upload(
                file_name="sample.dxf",
                file_bytes=(FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes(),
                fields={
                    "fabric_width": "10",
                    "unit": "cm",
                    "spacing": "0.2",
                    "seam_allowance_status": "included",
                    "seam_allowance_width": "0.5",
                    "nap_direction": "two_way",
                    "grainline_required": "false",
                    "allowed_rotation": "0",
                    "allowance_policy_mode": "fast_quote",
                    "fabric_type": "unknown",
                    "shrinkage_percent": "0",
                },
                store=JobStore(self.temp_dir / "jobs"),
                output_root=self.temp_dir / "output",
                web_base_url="http://127.0.0.1:8765",
            )

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
