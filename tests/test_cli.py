import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.cli import main


FIXTURE_DIR = ROOT / "tests" / "fixtures"


class FatternCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fattern-cli-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_estimate_writes_svg_and_report(self) -> None:
        output_dir = self.temp_dir / "out"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "estimate",
                    str(FIXTURE_DIR / "rectangle_lwpolyline.dxf"),
                    "--fabric-width",
                    "10",
                    "--unit",
                    "cm",
                    "--seam-allowance-included",
                    "yes",
                    "--one-way-fabric",
                    "no",
                    "--out",
                    str(output_dir),
                ]
            )

        self.assertEqual(code, 0, stderr.getvalue())
        response = json.loads(stdout.getvalue())
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["layout"]["marker_length"], 3.0)
        self.assertEqual(response["layout"]["efficiency"], 0.4)
        run_dir = Path(response["output_dir"])
        self.assertEqual(run_dir.parent, output_dir)
        self.assertTrue((run_dir / "marker_preview.svg").is_file())
        self.assertTrue((run_dir / "marker_report.md").is_file())
        self.assertTrue((run_dir / "result.json").is_file())
        self.assertIn("rectangle_lwpolyline", run_dir.name)
        self.assertIn("- marker_length: 3 cm", (run_dir / "marker_report.md").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((run_dir / "result.json").read_text(encoding="utf-8"))["status"], "completed")
        self.assertNotIn("fattern-jobs", stdout.getvalue())

    def test_estimate_can_use_input_directory_and_answers_json(self) -> None:
        input_dir = self.temp_dir / "input"
        input_dir.mkdir()
        shutil.copyfile(FIXTURE_DIR / "rectangle_lwpolyline.dxf", input_dir / "sample.dxf")
        (input_dir / "answers.json").write_text(
            json.dumps(
                {
                    "fabric_width": 10,
                    "unit": "cm",
                    "seam_allowance_included": "yes",
                    "one_way_fabric": "no",
                }
            ),
            encoding="utf-8",
        )
        output_dir = self.temp_dir / "output"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["estimate", "--input-dir", str(input_dir), "--out", str(output_dir)])

        self.assertEqual(code, 0, stderr.getvalue())
        response = json.loads(stdout.getvalue())
        run_dir = Path(response["output_dir"])
        self.assertTrue((run_dir / "result.json").is_file())
        self.assertIn("sample", run_dir.name)

    def test_one_way_fabric_without_grainline_returns_blocker(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "estimate",
                    str(FIXTURE_DIR / "rectangle_lwpolyline.dxf"),
                    "--fabric-width",
                    "10",
                    "--unit",
                    "cm",
                    "--seam-allowance-included",
                    "yes",
                    "--one-way-fabric",
                    "yes",
                    "--out",
                    str(self.temp_dir / "blocked"),
                ]
            )

        self.assertEqual(code, 1)
        response = json.loads(stderr.getvalue())
        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["stopped_at"], "estimate_marker_layout")
        self.assertEqual(response["errors"][0]["code"], "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC")

    def test_estimate_applies_default_seam_allowance_when_not_included(self) -> None:
        output_dir = self.temp_dir / "seam-out"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "estimate",
                    str(FIXTURE_DIR / "rectangle_lwpolyline.dxf"),
                    "--fabric-width",
                    "10",
                    "--unit",
                    "cm",
                    "--seam-allowance-included",
                    "no",
                    "--one-way-fabric",
                    "no",
                    "--out",
                    str(output_dir),
                ]
            )

        self.assertEqual(code, 0, stderr.getvalue())
        response = json.loads(stdout.getvalue())
        self.assertIn("SEAM_ALLOWANCE_ESTIMATED", [warning["code"] for warning in response["warnings"]])
        self.assertEqual(response["layout"]["marker_length"], 5.0)
        self.assertAlmostEqual(response["layout"]["efficiency"], 0.6)


if __name__ == "__main__":
    unittest.main()
