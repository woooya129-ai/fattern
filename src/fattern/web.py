"""Local browser UI for Fattern."""

from __future__ import annotations

from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
import json
import os
import sys
import webbrowser

from fattern.advisor import build_advisor_state
from fattern.hosting import (
    HOSTING_POLICY_PATH,
    MAX_REMOTE_MCP_BYTES,
    REMOTE_MCP_PATH,
    REMOTE_SERVER_MANIFEST_PATH,
    build_hosting_policy,
    build_remote_server_manifest,
)
from fattern.jobs import JobStore
from fattern.llm import ask_llm_advisor, llm_status
from fattern.mcp import McpToolRegistry
from fattern.mcp.http import (
    RemoteMcpHttpConfig,
    build_remote_mcp_dispatcher,
    send_mcp_get_not_supported,
    send_mcp_post,
)
from fattern.runs import (
    RunRecord,
    default_output_root,
    default_web_base_url,
    ensure_workspace_dirs,
    load_run_result,
    persist_run_outputs,
    resolve_run_file,
)
from fattern.schemas import SUPPORTED_UNITS


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_FORM_BYTES = 12 * 1024 * 1024
QUOTE_MODES = ("fast_quote", "sample_estimate", "bulk_precheck")
NAP_DIRECTIONS = ("two_way", "one_way", "none", "no_nap", "not_one_way")
FABRIC_TYPES = ("unknown", "woven", "knit")


@dataclass(frozen=True)
class WebEstimateResult:
    result: dict[str, Any]
    run: RunRecord | None = None
    archive_artifact_id: str | None = None


@dataclass
class WebServerConfig:
    output_root: Path
    web_base_url: str
    remote_mcp_enabled: bool = False
    remote_mcp_token: str | None = None
    allowed_origins: tuple[str, ...] = ()


def serve_web_ui(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = False,
    store: JobStore | None = None,
    output_root: Path | None = None,
    remote_mcp: bool = False,
    remote_mcp_token: str | None = None,
    public_base_url: str | None = None,
    allowed_origins: tuple[str, ...] = (),
) -> int:
    """Serve the local Web UI until interrupted."""

    ensure_workspace_dirs()
    token = remote_mcp_token if remote_mcp_token is not None else os.environ.get("FATTERN_REMOTE_MCP_TOKEN")
    if remote_mcp and _public_bind_host(host) and not token:
        raise ValueError("Remote MCP on a public bind host requires FATTERN_REMOTE_MCP_TOKEN or --bearer-token.")
    active_store = store or JobStore()
    active_output_root = output_root or default_output_root()
    config = WebServerConfig(
        output_root=active_output_root,
        web_base_url=public_base_url or "",
        remote_mcp_enabled=remote_mcp,
        remote_mcp_token=token,
        allowed_origins=allowed_origins,
    )
    server = ThreadingHTTPServer((host, port), _handler_class(active_store, config))
    url = _base_url(host, server.server_port, public_base_url)
    config.web_base_url = url
    print(f"Fattern Web UI: {url}", file=sys.stderr, flush=True)
    if remote_mcp:
        print(f"Fattern Remote MCP: {url.rstrip('/')}{REMOTE_MCP_PATH}", file=sys.stderr, flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def estimate_upload(
    *,
    file_name: str,
    file_bytes: bytes,
    fields: dict[str, str],
    store: JobStore | None = None,
    output_root: Path | None = None,
    web_base_url: str | None = None,
) -> WebEstimateResult:
    """Estimate from browser-uploaded bytes without exposing MCP base64 details."""

    if not file_bytes:
        raise ValueError("DXF file is required.")
    safe_name = Path(file_name or "upload.dxf").name
    fabric_width = _required_float(fields, "fabric_width")
    cuttable_width = _optional_float(fields.get("cuttable_width"))
    unit = _select(fields.get("unit"), SUPPORTED_UNITS, "cm")
    spacing = _optional_float(fields.get("spacing"))
    if spacing is None:
        spacing = 0.2
    shrinkage_percent = _optional_float(fields.get("shrinkage_percent"))
    if shrinkage_percent is None:
        shrinkage_percent = 0.0
    seam_allowance = _seam_allowance(fields)
    allowance_policy = {"mode": _select(fields.get("allowance_policy_mode"), QUOTE_MODES, "fast_quote")}

    active_store = store or JobStore()
    registry = McpToolRegistry(active_store, persist_runs=False)
    job = active_store.create_job(f"web:{Path(safe_name).stem}")
    file_id = active_store.register_input_file(job.job_id, safe_name, file_bytes)
    request: dict[str, Any] = {
        "schema_version": "1.0",
        "pattern_file_id": file_id,
        "fabric_width": fabric_width,
        "cuttable_width": cuttable_width,
        "unit": unit,
        "size_ratio": {},
        "piece_quantity": {},
        "spacing": spacing,
        "allowed_rotation": _rotations(fields.get("allowed_rotation")),
        "grainline_required": _bool(fields.get("grainline_required"), default=False),
        "nap_direction": _select(fields.get("nap_direction"), NAP_DIRECTIONS, "two_way"),
        "shrinkage_percent": shrinkage_percent,
        "fabric_type": _select(fields.get("fabric_type"), FABRIC_TYPES, "unknown"),
        "seam_allowance": seam_allowance,
        "allowance_policy": allowance_policy,
    }
    if cuttable_width is None:
        request.pop("cuttable_width")

    result = registry.call_tool("calculate_marker_yield", request)
    archive_artifact_id = None
    if result.get("status") == "completed":
        export_response = registry.call_tool(
            "export_artifacts",
            {
                "schema_version": "1.0",
                "job_id": job.job_id,
                "artifact_ids": result.get("export_artifact_ids", []),
                "archive_format": "zip",
            },
        )
        if not _has_blocker(export_response):
            archive_artifact_id = export_response.get("archive_artifact_id")
    persisted, run = persist_run_outputs(
        active_store,
        result,
        source_name=safe_name,
        output_root=output_root or default_output_root(),
        web_base_url=web_base_url if web_base_url is not None else default_web_base_url(),
    )
    return WebEstimateResult(result=persisted, run=run, archive_artifact_id=archive_artifact_id)


def _handler_class(store: JobStore, config: WebServerConfig) -> type[BaseHTTPRequestHandler]:
    class FatternWebHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(_render_page())
                return
            if parsed.path == REMOTE_MCP_PATH:
                if not config.remote_mcp_enabled:
                    self.send_error(404)
                    return
                send_mcp_get_not_supported(self)
                return
            if parsed.path == HOSTING_POLICY_PATH:
                self._send_json(
                    build_hosting_policy(
                        public_base_url=_request_base_url(self, config.web_base_url),
                        remote_mcp_enabled=config.remote_mcp_enabled,
                        auth_required=bool(config.remote_mcp_token),
                        max_upload_bytes=MAX_FORM_BYTES,
                        max_mcp_bytes=MAX_REMOTE_MCP_BYTES,
                    )
                )
                return
            if parsed.path == REMOTE_SERVER_MANIFEST_PATH:
                if not config.remote_mcp_enabled:
                    self.send_error(404)
                    return
                self._send_json(build_remote_server_manifest(public_base_url=_request_base_url(self, config.web_base_url)))
                return
            if parsed.path == "/healthz":
                self._send_json({"status": "ok", "remote_mcp_enabled": config.remote_mcp_enabled})
                return
            if parsed.path.startswith("/runs/"):
                self._send_run(parsed.path)
                return
            if parsed.path == "/artifact":
                self._send_artifact(parsed.query)
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            parsed_path = urlparse(self.path).path
            if parsed_path == REMOTE_MCP_PATH:
                if not config.remote_mcp_enabled:
                    self.send_error(404)
                    return
                dispatcher = build_remote_mcp_dispatcher(
                    store=store,
                    output_root=config.output_root,
                    web_base_url=_request_base_url(self, config.web_base_url),
                    allow_workspace_paths=False,
                )
                send_mcp_post(
                    self,
                    dispatcher=dispatcher,
                    config=RemoteMcpHttpConfig(
                        bearer_token=config.remote_mcp_token,
                        allowed_origins=config.allowed_origins,
                    ),
                )
                return
            if parsed_path == "/advisor":
                self._send_advisor()
                return
            if parsed_path != "/estimate":
                self.send_error(404)
                return
            try:
                fields, upload = _read_multipart(self)
                base_url = _request_base_url(self, config.web_base_url)
                estimate = estimate_upload(
                    file_name=upload[0],
                    file_bytes=upload[1],
                    fields=fields,
                    store=store,
                    output_root=config.output_root,
                    web_base_url=base_url,
                )
                self._send_html(_render_page(estimate))
            except Exception as exc:
                self._send_html(_render_page(error=str(exc)), status=400)

        def log_message(self, format: str, *args: object) -> None:
            print(f"fattern-ui: {format % args}", file=sys.stderr)

        def _send_html(self, html: str, *, status: int = 200) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_artifact(self, query: str) -> None:
            params = parse_qs(query)
            job_id = _single_param(params, "job_id")
            artifact_id = _single_param(params, "artifact_id")
            artifact = store.get_artifact(job_id, artifact_id)
            data = artifact.path.read_bytes()
            disposition = "attachment" if artifact.media_type in {"application/zip", "application/pdf"} else "inline"
            self.send_response(200)
            self.send_header("Content-Type", artifact.media_type)
            self.send_header("Content-Disposition", f'{disposition}; filename="{artifact.file_name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_run(self, path: str) -> None:
            parts = [part for part in path.split("/") if part]
            try:
                if len(parts) == 2:
                    run_id = parts[1]
                    result = load_run_result(run_id, config.output_root)
                    self._send_html(_render_run_page(run_id, result))
                    return
                if len(parts) == 3:
                    run_id, file_name = parts[1], parts[2]
                    self._send_run_file(run_id, file_name)
                    return
            except ValueError:
                self.send_error(404)
                return
            self.send_error(404)

        def _send_run_file(self, run_id: str, file_name: str) -> None:
            path = resolve_run_file(run_id, file_name, config.output_root)
            data = path.read_bytes()
            media_type = _media_type_for_file(path.name)
            disposition = "attachment" if path.suffix.lower() in {".zip", ".pdf", ".csv", ".json", ".txt"} else "inline"
            self.send_response(200)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Disposition", f'{disposition}; filename="{path.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_advisor(self) -> None:
            try:
                fields = _read_urlencoded(self)
                run_id = fields.get("run_id", "")
                message = fields.get("message", "")
                result = load_run_result(run_id, config.output_root)
                advisor_reply = ask_llm_advisor(user_message=message, result=result)
                self._send_html(_render_run_page(run_id, result, advisor_reply=advisor_reply))
            except ValueError:
                self.send_error(404)

    return FatternWebHandler


def _public_bind_host(host: str) -> bool:
    return host not in {"127.0.0.1", "localhost", "::1"}


def _base_url(host: str, port: int, public_base_url: str | None) -> str:
    if public_base_url:
        return public_base_url.rstrip("/")
    display_host = "127.0.0.1" if host in {"0.0.0.0", ""} else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{port}"


def _request_base_url(handler: BaseHTTPRequestHandler, configured_base_url: str) -> str:
    if configured_base_url:
        return configured_base_url.rstrip("/")
    host = handler.headers.get("Host")
    if host:
        scheme = "https" if handler.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
        return f"{scheme}://{host}".rstrip("/")
    server_host, server_port = handler.server.server_address[:2]
    return _base_url(str(server_host), int(server_port), None)


def _render_page(
    estimate: WebEstimateResult | None = None,
    *,
    error: str | None = None,
    advisor_reply: dict[str, Any] | None = None,
) -> str:
    result = estimate.result if estimate is not None else None
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fattern Local UI</title>
  <style>
    :root {{
      color-scheme: light;
      --border: #cbd5e1;
      --ink: #0f172a;
      --muted: #475569;
      --surface: #f8fafc;
      --accent: #2563eb;
      --danger: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: #ffffff;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
      display: grid;
      grid-template-columns: minmax(320px, 420px) 1fr;
      gap: 20px;
    }}
    h1 {{ font-size: 24px; margin: 0 0 16px; }}
    h2 {{ font-size: 18px; margin: 0 0 12px; }}
    form, .panel {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      background: var(--surface);
    }}
    label {{ display: grid; gap: 6px; font-size: 13px; color: var(--muted); margin-bottom: 12px; }}
    input, select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 14px;
      color: var(--ink);
      background: #ffffff;
    }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .stack {{ display: grid; gap: 16px; }}
    .notice {{ margin: 0 0 14px; color: var(--muted); line-height: 1.45; }}
    button {{
      width: 100%;
      min-height: 42px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #ffffff;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }}
    textarea {{
      width: 100%;
      min-height: 92px;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 14px;
      resize: vertical;
    }}
    .error {{ color: var(--danger); border-color: #fecaca; background: #fff1f2; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .metric {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 18px; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 16px; }}
    .links a {{
      color: var(--accent);
      text-decoration: none;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 7px 10px;
      background: #ffffff;
    }}
    .small-list {{ margin: 0; padding-left: 18px; color: var(--muted); line-height: 1.45; }}
    .message-list {{ display: grid; gap: 8px; }}
    .message {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      background: #ffffff;
    }}
    .message strong {{ display: block; margin-bottom: 4px; }}
    .message code {{ color: var(--muted); }}
    img {{ width: 100%; max-height: 720px; object-fit: contain; border: 1px solid var(--border); background: #ffffff; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 8px; }}
    @media (max-width: 860px) {{
      main {{ grid-template-columns: 1fr; padding: 14px; }}
      .summary {{ grid-template-columns: 1fr; }}
      .row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Fattern Local UI</h1>
      {_render_error(error)}
      {_render_form()}
    </section>
    <section class="stack">
      {_render_result(estimate)}
      {_render_advisor_panel(result, advisor_reply=advisor_reply)}
    </section>
  </main>
</body>
</html>"""


def _render_form() -> str:
    return """<form action="/estimate" method="post" enctype="multipart/form-data">
  <h2>질문지</h2>
  <p class="notice">Fattern은 DXF 패턴으로 rough marker와 견적용 가요척을 계산한다. 생산 확정용 CAD nesting 대체품은 아니다. 모르는 값은 기본값으로 시작해도 된다.</p>
  <label>DXF file<input name="dxf_file" type="file" accept=".dxf" required></label>
  <div class="row">
    <label>Fabric width<input name="fabric_width" type="number" min="1" step="0.001" value="150" required></label>
    <label>Cuttable width<input name="cuttable_width" type="number" min="1" step="0.001" placeholder="optional"></label>
  </div>
  <div class="row">
    <label>Unit
      <select name="unit">
        <option value="cm" selected>cm</option><option value="mm">mm</option><option value="m">m</option>
        <option value="inch">inch</option><option value="ft">ft</option><option value="yd">yd</option>
      </select>
    </label>
    <label>Spacing<input name="spacing" type="number" min="0" step="0.001" value="0.2"></label>
  </div>
  <div class="row">
    <label>Seam allowance
      <select name="seam_allowance_status">
        <option value="included" selected>included</option>
        <option value="excluded">excluded</option>
      </select>
    </label>
    <label>Fallback width<input name="seam_allowance_width" type="number" min="0" step="0.001" placeholder="default 1/2 inch"></label>
  </div>
  <div class="row">
    <label>Nap direction
      <select name="nap_direction">
        <option value="two_way" selected>two_way</option><option value="one_way">one_way</option>
        <option value="none">none</option><option value="no_nap">no_nap</option><option value="not_one_way">not_one_way</option>
      </select>
    </label>
    <label>Grainline required
      <select name="grainline_required">
        <option value="false" selected>false</option><option value="true">true</option>
      </select>
    </label>
  </div>
  <div class="row">
    <label>Rotation
      <select name="allowed_rotation">
        <option value="0" selected>0</option><option value="0,180">0,180</option><option value="0,90,180,270">0,90,180,270</option>
      </select>
    </label>
    <label>Quote mode
      <select name="allowance_policy_mode">
        <option value="fast_quote" selected>fast_quote</option>
        <option value="sample_estimate">sample_estimate</option>
        <option value="bulk_precheck">bulk_precheck</option>
      </select>
    </label>
  </div>
  <div class="row">
    <label>Fabric type
      <select name="fabric_type">
        <option value="unknown" selected>unknown</option><option value="woven">woven</option><option value="knit">knit</option>
      </select>
    </label>
    <label>Shrinkage %<input name="shrinkage_percent" type="number" min="0" step="0.001" value="0"></label>
  </div>
  <button type="submit">Calculate</button>
</form>"""


def _render_error(error: str | None) -> str:
    if not error:
        return ""
    return f'<div class="panel error">{escape(error)}</div>'


def _render_result(estimate: WebEstimateResult | None) -> str:
    if estimate is None:
        return '<div class="panel"><h2>Result</h2><p class="notice">DXF를 업로드하면 preview와 산출물 링크가 여기에 표시된다.</p></div>'
    result = estimate.result
    if result.get("status") != "completed":
        return f"""<div class="panel error">
  <h2>Blocked</h2>
  <div class="links">{_result_links(result, estimate.archive_artifact_id)}</div>
  <pre>{escape(json.dumps(_public_result(result), ensure_ascii=False, indent=2))}</pre>
</div>"""

    job_id = str(result["job_id"])
    artifacts = result.get("artifact_ids", {})
    preview_url = result.get("preview_url") or _artifact_url(job_id, artifacts.get("marker_preview_svg"))
    links = _result_links(result, estimate.archive_artifact_id)
    minimum = _yield_text(result.get("minimum_yield"), "marker_length")
    quote = _yield_text(result.get("quote_yield"), "final_yield")
    confidence = escape(str(result.get("confidence", {}).get("grade", "unknown")))
    return f"""<div class="panel">
  <h2>Result</h2>
  <div class="summary">
    <div class="metric"><span>minimum_yield</span><strong>{minimum}</strong></div>
    <div class="metric"><span>quote_yield</span><strong>{quote}</strong></div>
    <div class="metric"><span>confidence</span><strong>{confidence}</strong></div>
  </div>
  <div class="links">{links}</div>
  {f'<img src="{preview_url}" alt="marker preview">' if preview_url else ''}
</div>"""


def _render_run_page(
    run_id: str,
    result: dict[str, Any],
    *,
    advisor_reply: dict[str, Any] | None = None,
) -> str:
    return _render_page(WebEstimateResult(result=result), advisor_reply=advisor_reply)


def _result_links(result: dict[str, Any], archive_artifact_id: str | None = None) -> str:
    run_id = result.get("run_id")
    if isinstance(run_id, str) and run_id:
        labels = {
            "marker_preview.svg": "SVG",
            "marker_report.md": "Markdown",
            "marker_report.pdf": "PDF",
            "report.csv": "CSV",
            "result.json": "JSON",
            "run_summary.txt": "Summary",
        }
        files = result.get("run_files")
        available = set(files) if isinstance(files, list) else set(labels)
        links = [
            f'<a href="/runs/{escape(run_id)}/{file_name}">{label}</a>'
            for file_name, label in labels.items()
            if file_name in available
        ]
        return "".join(links)
    job_id = str(result.get("job_id", ""))
    artifacts = result.get("artifact_ids", {})
    return _artifact_links(job_id, artifacts if isinstance(artifacts, dict) else {}, archive_artifact_id)


def _render_advisor_panel(
    result: dict[str, Any] | None,
    *,
    advisor_reply: dict[str, Any] | None = None,
) -> str:
    status = llm_status()
    state = build_advisor_state(result, llm_available=bool(status.get("available")))
    field_items = "".join(
        f"<li><strong>{escape(item['title'])}</strong>: {escape(item['text'])}</li>"
        for item in state["field_help"]
    )
    next_steps = "".join(f"<li>{escape(step)}</li>" for step in state["next_steps"])
    messages = _render_advisor_messages(state["messages"])
    llm_block = _render_llm_block(result, status, advisor_reply)
    return f"""<div class="panel">
  <h2>Advisor</h2>
  <p class="notice">계산은 Fattern engine이 하고, Advisor는 입력값과 warning을 설명한다.</p>
  <h3>다음 단계</h3>
  <ul class="small-list">{next_steps}</ul>
  <h3>입력 도움말</h3>
  <ul class="small-list">{field_items}</ul>
  {messages}
  {llm_block}
</div>"""


def _render_advisor_messages(messages: list[dict[str, str]]) -> str:
    if not messages:
        return ""
    items = []
    for message in messages:
        items.append(
            f"""<div class="message">
  <strong>{escape(message['title'])}</strong>
  <code>{escape(message['code'])}</code>
  <p>{escape(message['action'])}</p>
</div>"""
        )
    return '<h3>Warning / Blocker</h3><div class="message-list">' + "".join(items) + "</div>"


def _render_llm_block(
    result: dict[str, Any] | None,
    status: dict[str, str | bool],
    advisor_reply: dict[str, Any] | None,
) -> str:
    reply_html = ""
    if advisor_reply is not None:
        if advisor_reply.get("status") == "completed":
            reply_html = f'<div class="message"><strong>LLM answer</strong><p>{escape(str(advisor_reply.get("answer", "")))}</p></div>'
        else:
            reply_html = f'<div class="message"><strong>LLM disabled</strong><p>{escape(str(advisor_reply.get("message", "")))}</p></div>'
    run_id = result.get("run_id") if isinstance(result, dict) else None
    if not run_id:
        return reply_html + '<p class="notice">LLM Advisor는 계산 결과가 있을 때만 사용할 수 있다.</p>'
    if not status.get("available"):
        return reply_html + f'<p class="notice">LLM Advisor disabled: {escape(str(status.get("reason", "")))}</p>'
    return reply_html + f"""<form action="/advisor" method="post">
  <h3>LLM Advisor</h3>
  <input type="hidden" name="run_id" value="{escape(str(run_id))}">
  <label>Question<textarea name="message" maxlength="2000" placeholder="이 결과에서 견적 리스크를 설명해줘"></textarea></label>
  <button type="submit">Ask Advisor</button>
</form>"""


def _artifact_links(job_id: str, artifacts: dict[str, Any], archive_artifact_id: str | None) -> str:
    labels = {
        "marker_preview_svg": "SVG",
        "marker_report_md": "Markdown",
        "marker_report_pdf": "PDF",
        "report_csv": "CSV",
        "result_json": "JSON",
    }
    links = []
    for key, label in labels.items():
        url = _artifact_url(job_id, artifacts.get(key))
        if url:
            links.append(f'<a href="{url}">{label}</a>')
    if archive_artifact_id:
        links.append(f'<a href="{_artifact_url(job_id, archive_artifact_id)}">ZIP</a>')
    return "".join(links)


def _artifact_url(job_id: str, artifact_id: object) -> str:
    if not isinstance(artifact_id, str) or not artifact_id:
        return ""
    return "/artifact?" + urlencode({"job_id": job_id, "artifact_id": artifact_id})


def _yield_text(value: object, field: str) -> str:
    if not isinstance(value, dict):
        return "n/a"
    amount = value.get(field)
    unit = value.get("unit") or value.get("policy_unit") or ""
    if isinstance(amount, (int, float)) and not isinstance(amount, bool):
        text = f"{amount:.6f}".rstrip("0").rstrip(".")
        return escape(f"{text} {unit}".strip())
    return "n/a"


def _read_multipart(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], tuple[str, bytes]]:
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > MAX_FORM_BYTES:
        raise ValueError("Upload is missing or too large.")
    body = handler.rfile.read(length)
    fields, files = parse_multipart_form(content_type, body)
    upload = files.get("dxf_file")
    if upload is None:
        raise ValueError("DXF file is required.")
    return fields, upload


def _read_urlencoded(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > 64_000:
        raise ValueError("Form body is missing or too large.")
    body = handler.rfile.read(length).decode("utf-8", errors="replace")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def _media_type_for_file(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    return {
        ".svg": "image/svg+xml",
        ".md": "text/markdown; charset=utf-8",
        ".pdf": "application/pdf",
        ".csv": "text/csv; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }.get(suffix, "application/octet-stream")


def parse_multipart_form(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    if "multipart/form-data" not in content_type:
        raise ValueError("Expected multipart form upload.")
    raw = b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    message = BytesParser(policy=default).parsebytes(raw)
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename is not None:
            files[name] = (filename, payload)
        else:
            charset = part.get_content_charset() or "utf-8"
            fields[name] = payload.decode(charset, errors="replace")
    return fields, files


def _single_param(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key)
    if not values:
        raise ValueError(f"{key} is required.")
    return values[0]


def _required_float(fields: dict[str, str], key: str) -> float:
    value = _optional_float(fields.get(key))
    if value is None:
        raise ValueError(f"{key} is required.")
    return value


def _optional_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError("Numeric fields must contain numbers.") from exc
    if number < 0:
        raise ValueError("Numeric fields must be zero or greater.")
    return number


def _bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"true", "yes", "1", "on"}


def _select(value: str | None, allowed: tuple[str, ...] | list[str], default_value: str) -> str:
    normalized = (value or default_value).strip()
    return normalized if normalized in allowed else default_value


def _rotations(value: str | None) -> list[int]:
    if not value:
        return [0]
    rotations = []
    for item in value.split(","):
        try:
            rotation = int(item.strip())
        except ValueError:
            continue
        if rotation in {0, 90, 180, 270} and rotation not in rotations:
            rotations.append(rotation)
    return rotations or [0]


def _seam_allowance(fields: dict[str, str]) -> dict[str, Any]:
    status = _select(fields.get("seam_allowance_status"), ("included", "excluded"), "included")
    seam_allowance: dict[str, Any] = {"status": status}
    fallback_width = _optional_float(fields.get("seam_allowance_width"))
    if fallback_width is not None:
        seam_allowance["fallback_width"] = fallback_width
    return seam_allowance


def _has_blocker(response: dict[str, Any]) -> bool:
    return any(error.get("severity") == "blocker" for error in response.get("errors", []))


def _public_result(response: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in response.items() if key != "store"}
