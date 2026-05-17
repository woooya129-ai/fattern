import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.engine import EngineMessage, LayoutPlacement, LayoutResult
from fattern.jobs import FileRecord, JobError, JobStore


def layout_result(piece_id: str = "piece_0001") -> LayoutResult:
    return LayoutResult(
        placements=(LayoutPlacement(piece_id, "OUTLINE", 0.0, 0.0, 4.0, 3.0, 0),),
        fabric_width=10.0,
        marker_length=3.0,
        efficiency=0.4,
        clearance=0.2,
        unit="cm",
        no_overlap=True,
        messages=(EngineMessage("LAYOUT_ESTIMATED", "Layout estimated.", "info"),),
        total_piece_area=12.0,
        rotation_allowed_degrees=(0, 180),
    )


class JobStoreLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="fattern-job-store-test-")
        self.store = JobStore(Path(self.temp_dir) / "jobs")
        self.job = self.store.create_job("sample")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_store_and_get_layout_returns_server_side_result(self) -> None:
        result = layout_result()

        layout_id = self.store.store_layout(self.job.job_id, result)
        stored = self.store.get_layout(self.job.job_id, layout_id)

        self.assertTrue(layout_id.startswith("layout_"))
        self.assertIs(stored, result)

    def test_get_layout_missing_id_returns_public_error_without_paths(self) -> None:
        with self.assertRaises(JobError) as raised:
            self.store.get_layout(self.job.job_id, "layout_missing")

        self.assertEqual(raised.exception.code, "LAYOUT_NOT_FOUND")
        self.assertNotIn(str(self.store.root), raised.exception.public_message)
        self.assertNotIn(self.temp_dir, raised.exception.public_message)

    def test_layout_prefix_collision_generates_new_id(self) -> None:
        with patch("fattern.jobs.store.secrets.token_hex", side_effect=["same", "same", "next"]):
            first_id = self.store.store_layout(self.job.job_id, layout_result("piece_0001"))
            second_id = self.store.store_layout(self.job.job_id, layout_result("piece_0002"))

        self.assertEqual(first_id, "layout_same")
        self.assertEqual(second_id, "layout_next")
        self.assertEqual(self.store.get_layout(self.job.job_id, first_id).placements[0].piece_id, "piece_0001")
        self.assertEqual(self.store.get_layout(self.job.job_id, second_id).placements[0].piece_id, "piece_0002")

    def test_resolve_input_file_maps_file_id_back_to_job_workspace(self) -> None:
        file_id = self.store.register_input_file(self.job.job_id, "sample.dxf", b"0\nEOF\n")

        job_record, file_record = self.store.resolve_input_file(file_id)

        self.assertEqual(job_record.job_id, self.job.job_id)
        self.assertIsInstance(file_record, FileRecord)
        self.assertEqual(file_record.file_id, file_id)
        self.assertEqual(file_record.original_name, "sample.dxf")


if __name__ == "__main__":
    unittest.main()
