import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.jobs import ArtifactRecord, JobStore, SecurityError
from fattern.mcp import McpToolRegistry


class ArtifactExportSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="fattern-artifact-security-test-")
        self.store = JobStore(Path(self.temp_dir) / "jobs")
        self.registry = McpToolRegistry(self.store)
        self.job_id = self.registry.call_tool("create_job", {"schema_version": "1.0", "job_name": "sample"})["job_id"]

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_register_artifact_rejects_path_tokens_and_unsupported_types(self) -> None:
        rejected_names = [
            "../result.json",
            r"C:\result.json",
            "file:///result.json",
            r"\\server\share\result.json",
            "result.json:ads",
            "debug.log",
        ]
        for name in rejected_names:
            with self.subTest(name=name):
                with self.assertRaises(SecurityError):
                    self.store.register_artifact(self.job_id, name, "{}")

    def test_export_artifacts_blocks_non_exportable_manifest_item(self) -> None:
        artifact_id = self.store.register_artifact(
            self.job_id,
            "partial.json",
            "{}",
            media_type="application/json",
            exportable=False,
        )

        response = self.registry.call_tool(
            "export_artifacts",
            {"schema_version": "1.0", "job_id": self.job_id, "artifact_ids": [artifact_id]},
        )

        self.assertEqual(response["errors"][0]["code"], "ARTIFACT_NOT_EXPORTABLE")

    def test_export_artifacts_blocks_logs_directory_manifest_tampering(self) -> None:
        record = self.store.get_job(self.job_id)
        log_path = record.workspace_root / "logs" / "secret.json"
        log_path.write_text('{"secret": true}', encoding="utf-8")
        record.artifacts["artifact_log"] = ArtifactRecord(
            artifact_id="artifact_log",
            path=log_path,
            file_name="secret.json",
            media_type="application/json",
        )

        response = self.registry.call_tool(
            "export_artifacts",
            {"schema_version": "1.0", "job_id": self.job_id, "artifact_ids": ["artifact_log"]},
        )

        serialized = json.dumps(response)
        self.assertEqual(response["errors"][0]["code"], "FILE_ACCESS_BLOCKED")
        self.assertNotIn(str(self.store.root), serialized)
        self.assertNotIn(self.temp_dir, serialized)

    def test_export_artifacts_blocks_zip_slip_manifest_entry(self) -> None:
        artifact_id = self.store.register_artifact(self.job_id, "result.json", "{}", media_type="application/json")
        record = self.store.get_job(self.job_id)
        artifact = record.artifacts[artifact_id]
        record.artifacts[artifact_id] = ArtifactRecord(
            artifact_id="../escape",
            path=artifact.path,
            file_name=artifact.file_name,
            media_type=artifact.media_type,
        )

        response = self.registry.call_tool(
            "export_artifacts",
            {"schema_version": "1.0", "job_id": self.job_id, "artifact_ids": [artifact_id]},
        )

        self.assertEqual(response["errors"][0]["code"], "ZIP_SLIP_BLOCKED")
        self.assertNotIn(str(self.store.root), json.dumps(response))


if __name__ == "__main__":
    unittest.main()
