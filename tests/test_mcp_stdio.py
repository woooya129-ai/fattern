import json
import os
import subprocess
import sys
import unittest
from base64 import b64encode
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.mcp.stdio import FatternStdioMcpServer


FIXTURE_DIR = ROOT / "tests" / "fixtures"


def request(request_id: int, method: str, params: dict | None = None) -> dict:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


class McpStdioTransportTests(unittest.TestCase):
    def test_stdio_subprocess_handles_initialize_tools_list_and_tool_call(self) -> None:
        messages = [
            request(
                1,
                "initialize",
                {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
            ),
            request(2, "tools/list", {}),
            request(3, "tools/call", {"name": "create_job", "arguments": {"schema_version": "1.0", "job_name": "stdio"}}),
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")

        completed = subprocess.run(
            [sys.executable, "-m", "fattern", "mcp-stdio"],
            cwd=ROOT,
            input="\n".join(json.dumps(item) for item in messages) + "\n",
            capture_output=True,
            encoding="utf-8",
            env=env,
            timeout=10,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([response["id"] for response in responses], [1, 2, 3])
        self.assertEqual(
            responses[0]["result"]["capabilities"],
            {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
        )
        tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertIn("register_input_file", tool_names)
        self.assertIn("parse_dxf", tool_names)
        self.assertFalse(responses[2]["result"]["isError"])
        self.assertTrue(responses[2]["result"]["structuredContent"]["job_id"].startswith("job_"))

    def test_stdio_dispatcher_can_register_and_parse_file_content_without_paths(self) -> None:
        server = FatternStdioMcpServer()
        create_response = server.handle_message(
            request(1, "tools/call", {"name": "create_job", "arguments": {"schema_version": "1.0", "job_name": "chain"}})
        )
        job_id = create_response["result"]["structuredContent"]["job_id"]
        encoded = b64encode((FIXTURE_DIR / "rectangle_lwpolyline.dxf").read_bytes()).decode("ascii")

        register_response = server.handle_message(
            request(
                2,
                "tools/call",
                {
                    "name": "register_input_file",
                    "arguments": {
                        "schema_version": "1.0",
                        "job_id": job_id,
                        "file_name": "sample.dxf",
                        "content_base64": encoded,
                    },
                },
            )
        )
        file_id = register_response["result"]["structuredContent"]["file_id"]
        parse_response = server.handle_message(
            request(
                3,
                "tools/call",
                {
                    "name": "parse_dxf",
                    "arguments": {"schema_version": "1.0", "job_id": job_id, "file_id": file_id, "unit_hint": "cm"},
                },
            )
        )

        parse_result = parse_response["result"]
        self.assertFalse(parse_result["isError"])
        self.assertEqual(parse_result["structuredContent"]["entity_summary"]["entity_count"], 1)
        self.assertNotIn(str(ROOT), json.dumps(parse_result))

    def test_stdio_dispatcher_returns_protocol_error_for_unknown_method(self) -> None:
        response = FatternStdioMcpServer().handle_message(request(1, "unknown/method", {}))

        self.assertEqual(response["error"]["code"], -32601)

    def test_stdio_dispatcher_exposes_slash_prompt_help(self) -> None:
        server = FatternStdioMcpServer()
        list_response = server.handle_message(request(1, "prompts/list", {}))
        prompt_names = {prompt["name"] for prompt in list_response["result"]["prompts"]}

        self.assertIn("fattern-help", prompt_names)
        get_response = server.handle_message(request(2, "prompts/get", {"name": "fattern-estimate", "arguments": {}}))
        text = get_response["result"]["messages"][0]["content"]["text"]
        self.assertIn("Default rotation is 0 only", text)


if __name__ == "__main__":
    unittest.main()
