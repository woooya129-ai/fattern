import unittest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.advisor import build_advisor_state, explain_message
from fattern.llm import ask_llm_advisor, build_llm_context, llm_status


class AdvisorLlmTests(unittest.TestCase):
    def test_deterministic_advisor_explains_known_warning(self) -> None:
        explanation = explain_message("GRAINLINE_NOT_DETECTED", "No grainline.")

        self.assertIn("식서", explanation["title"])
        self.assertEqual(explanation["code"], "GRAINLINE_NOT_DETECTED")

    def test_advisor_state_includes_blocker_next_steps(self) -> None:
        state = build_advisor_state(
            {
                "status": "blocked",
                "errors": [{"code": "MISSING_GRAINLINE_REQUIRED", "message": "missing", "severity": "blocker"}],
                "warnings": [],
            }
        )

        self.assertEqual(state["status"], "blocked")
        self.assertIn("blocked 결과는 견적 요척으로 사용하지 않는다.", state["next_steps"])
        self.assertEqual(state["messages"][0]["code"], "MISSING_GRAINLINE_REQUIRED")

    def test_llm_context_excludes_artifact_ids_and_paths(self) -> None:
        context = build_llm_context(
            {
                "status": "completed",
                "job_id": "job_secret",
                "artifact_ids": {"result_json": "artifact_secret"},
                "output_dir": r"C:\secret\output",
                "web_url": "http://127.0.0.1:8765/runs/secret",
                "preview_url": "http://127.0.0.1:8765/runs/secret/marker_preview.svg",
                "source_name": "secret.dxf",
                "content_base64": "DXF_BYTES_SHOULD_NOT_LEAK",
                "layout": {"marker_length": 3.0},
                "warnings": [{"code": "REPORT_CSV_PARTIAL_FIELDS", "message": "partial", "severity": "warning"}],
            }
        )

        serialized = str(context)
        self.assertNotIn("job_secret", serialized)
        self.assertNotIn("artifact_secret", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("DXF_BYTES_SHOULD_NOT_LEAK", serialized)
        self.assertEqual(context["layout"], {"marker_length": 3.0})

    def test_llm_status_disabled_without_server_config(self) -> None:
        status = llm_status({})

        self.assertFalse(status["available"])

    def test_openai_llm_adapter_uses_server_side_key_only(self) -> None:
        calls = []

        def fake_post(url, headers, payload):
            calls.append((url, headers, payload))
            return {"output_text": "Use quote_yield as an estimate."}

        response = ask_llm_advisor(
            user_message="Explain this result.",
            result={"status": "completed", "quote_yield": {"final_yield": 4.5, "unit": "cm"}},
            environ={
                "FATTERN_LLM_PROVIDER": "openai",
                "FATTERN_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "server-secret",
            },
            http_post=fake_post,
        )

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["answer"], "Use quote_yield as an estimate.")
        self.assertEqual(calls[0][0], "https://api.openai.com/v1/responses")
        self.assertEqual(calls[0][1]["Authorization"], "Bearer server-secret")
        self.assertNotIn("artifact_ids", str(calls[0][2]))

    def test_anthropic_llm_adapter_uses_messages_endpoint(self) -> None:
        calls = []

        def fake_post(url, headers, payload):
            calls.append((url, headers, payload))
            return {"content": [{"type": "text", "text": "Check warning codes first."}]}

        response = ask_llm_advisor(
            user_message="What should I check?",
            result={"status": "completed", "warnings": []},
            environ={
                "FATTERN_LLM_PROVIDER": "anthropic",
                "FATTERN_LLM_MODEL": "test-claude",
                "ANTHROPIC_API_KEY": "server-anthropic-secret",
            },
            http_post=fake_post,
        )

        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["answer"], "Check warning codes first.")
        self.assertEqual(calls[0][0], "https://api.anthropic.com/v1/messages")
        self.assertEqual(calls[0][1]["x-api-key"], "server-anthropic-secret")
        self.assertEqual(calls[0][1]["anthropic-version"], "2023-06-01")


if __name__ == "__main__":
    unittest.main()
