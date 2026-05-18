import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fattern.jobs import JobStore
from fattern.web import WebServerConfig, _handler_class


class RemoteMcpHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fattern-http-mcp-test-"))
        self.store = JobStore(self.temp_dir / "jobs")
        self.config = WebServerConfig(
            output_root=self.temp_dir / "output",
            web_base_url="",
            remote_mcp_enabled=True,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_class(self.store, self.config))
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.config.web_base_url = self.base_url
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_hosting_policy_and_manifest_expose_remote_mcp_contract(self) -> None:
        health = self._get_json("/healthz")
        policy = self._get_json("/hosting/policy")
        manifest = self._get_json("/server.json")

        self.assertEqual(health["status"], "ok")
        self.assertEqual(policy["remote_mcp"]["endpoint"], f"{self.base_url}/mcp")
        self.assertEqual(policy["remote_mcp"]["transport"], "streamable-http-json-response")
        self.assertFalse(policy["remote_mcp"]["workspace_path_tools"])
        self.assertEqual(policy["security_policy"]["oauth_status"], "not_implemented_in_v0.9.0_preparation")
        self.assertEqual(manifest["remotes"][0], {"type": "streamable-http", "url": f"{self.base_url}/mcp"})

    def test_plain_ui_exposes_diagnostics_but_not_remote_mcp_endpoints(self) -> None:
        self.config.remote_mcp_enabled = False

        health = self._get_json("/healthz")
        policy = self._get_json("/hosting/policy")

        self.assertEqual(health["status"], "ok")
        self.assertFalse(health["remote_mcp_enabled"])
        self.assertFalse(policy["remote_mcp"]["enabled"])
        with self.assertRaises(HTTPError) as mcp_error:
            urlopen(Request(f"{self.base_url}/mcp", method="GET"), timeout=10)
        self.assertEqual(mcp_error.exception.code, 404)
        mcp_error.exception.close()
        with self.assertRaises(HTTPError) as manifest_error:
            urlopen(Request(f"{self.base_url}/server.json", method="GET"), timeout=10)
        self.assertEqual(manifest_error.exception.code, 404)
        manifest_error.exception.close()

    def test_mcp_post_lists_remote_safe_tools_without_workspace_path_tool(self) -> None:
        response = self._post_mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

        tool_names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("register_input_file", tool_names)
        self.assertIn("calculate_marker_yield", tool_names)
        self.assertNotIn("estimate_workspace_dxf", tool_names)

    def test_mcp_post_blocks_workspace_path_tool_even_if_called_directly(self) -> None:
        response = self._post_mcp(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "estimate_workspace_dxf",
                    "arguments": {
                        "schema_version": "1.0",
                        "relative_path": "input/sample.dxf",
                        "fabric_width": 150,
                        "unit": "cm",
                    },
                },
            }
        )

        structured = response["result"]["structuredContent"]
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(structured["errors"][0]["code"], "WORKSPACE_PATHS_DISABLED")

    def test_mcp_prompt_uses_remote_file_flow(self) -> None:
        response = self._post_mcp(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "prompts/get",
                "params": {"name": "fattern", "arguments": {}},
            }
        )

        text = response["result"]["messages"][0]["content"]["text"]
        self.assertIn("register_input_file", text)
        self.assertIn("estimate_workspace_dxf", text)
        self.assertIn("disabled on remote MCP", text)

    def test_mcp_post_can_require_bearer_token(self) -> None:
        self.config.remote_mcp_token = "secret"
        with self.assertRaises(HTTPError) as unauthorized:
            self._post_mcp({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
        self.assertEqual(unauthorized.exception.code, 401)
        unauthorized.exception.close()

        response = self._post_mcp(
            {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}},
            authorization="Bearer secret",
        )

        self.assertEqual(response["result"], {})

    def test_mcp_get_returns_405_until_sse_streaming_is_implemented(self) -> None:
        request = Request(f"{self.base_url}/mcp", method="GET")

        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=10)

        self.assertEqual(error.exception.code, 405)
        error.exception.close()

    def _get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_mcp(self, payload: dict, *, authorization: str | None = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if authorization is not None:
            headers["Authorization"] = authorization
        request = Request(
            f"{self.base_url}/mcp",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
