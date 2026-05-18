"""Deterministic advisor copy for Web UI and MCP-facing summaries."""

from __future__ import annotations

from typing import Any


FIELD_HELP = (
    {
        "field": "fabric_width",
        "title": "Fabric width",
        "text": "원단 전체 폭이다. 모르면 실제 원단 라벨이나 거래처 스펙의 폭을 넣는다.",
    },
    {
        "field": "cuttable_width",
        "title": "Cuttable width",
        "text": "셀비지와 가장자리 불량을 뺀 실제 배치 가능 폭이다. 입력하면 fabric_width보다 우선한다.",
    },
    {
        "field": "seam_allowance",
        "title": "Seam allowance",
        "text": "패턴에 시접이 이미 있으면 included다. 없으면 excluded이고 기본 1/2 inch가 적용된다.",
    },
    {
        "field": "nap_direction",
        "title": "Nap direction",
        "text": "방향성이 있는 원단은 one_way다. 일반 양방향 배치가 가능하면 two_way를 쓴다.",
    },
    {
        "field": "grainline_required",
        "title": "Grainline required",
        "text": "식서 방향 검증이 꼭 필요하면 true다. woven이나 one_way 조건에서는 누락 시 차단될 수 있다.",
    },
    {
        "field": "quote_yield",
        "title": "Quote yield",
        "text": "minimum_yield에 견적용 여유분, 경고 기반 리스크, 반올림을 더한 값이다. 생산 확정 요척은 아니다.",
    },
)


MESSAGE_HELP = {
    "GRAINLINE_NOT_DETECTED": (
        "식서선이 감지되지 않았다.",
        "원웨이 원단이나 woven 검토라면 DXF에 식서선을 명확한 layer로 넣고 다시 계산한다.",
    ),
    "MISSING_GRAINLINE_REQUIRED": (
        "식서 필수 조건인데 piece-level 식서선이 없다.",
        "grainline_required를 false로 낮추거나, DXF에 식서선을 추가한다.",
    ),
    "MISSING_GRAINLINE_FOR_WOVEN": (
        "woven 원단인데 식서선이 없다.",
        "woven 검토는 식서 방향이 중요하므로 DXF 식서 layer를 정리해야 한다.",
    ),
    "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC": (
        "원웨이 원단인데 식서선이 없다.",
        "원웨이 배치는 방향 검증 없이 계산하면 위험하므로 식서선이 필요하다.",
    ),
    "SEAM_ALLOWANCE_DEFAULT_APPLIED": (
        "시접 미포함으로 보고 기본 시접을 적용했다.",
        "기본값은 1/2 inch다. 실제 시접이 다르면 fallback width를 직접 입력한다.",
    ),
    "SEAM_ALLOWANCE_ESTIMATED": (
        "시접이 rough 방식으로 확장됐다.",
        "곡선 offset CAD 처리와 같지 않으므로 생산 확정값으로 보지 않는다.",
    ),
    "CUTTABLE_WIDTH_APPLIED": (
        "cuttable_width가 fabric_width보다 우선 적용됐다.",
        "셀비지 제외 폭 기준 결과이므로 실제 재단 가능 폭이 맞는지 확인한다.",
    ),
    "REPORT_CSV_PARTIAL_FIELDS": (
        "CSV 일부 metadata 필드가 비어 있다.",
        "DXF에 piece name, size, grainline 정보가 없으면 해당 칸은 비어 있을 수 있다.",
    ),
    "DXF_UNIT_AUTOSCALE_APPLIED": (
        "DXF 좌표 단위를 자동 추정해 스케일을 적용했다.",
        "결과 길이가 이상하면 CAD export 단위와 원단 폭 단위를 확인한다.",
    ),
    "UNVERIFIED_DXF_VERSION": (
        "검증되지 않은 DXF 버전이지만 파싱을 계속했다.",
        "결과 preview에서 외곽선이 제대로 읽혔는지 확인한다.",
    ),
    "AAMA_ASTM_LAYER_MAPPING_UNVERIFIED": (
        "숫자 layer의 AAMA/ASTM 의미를 낮은 신뢰도로만 처리했다.",
        "vendor별 layer 규칙이 다를 수 있으므로 layer_audit를 확인한다.",
    ),
    "INTERNAL_LINE_EXCLUDED": (
        "내부선으로 판단된 LINE entity가 면적 계산에서 제외됐다.",
        "외곽선이 LINE 조각으로만 된 DXF라면 preview에서 누락이 없는지 확인한다.",
    ),
    "SIZE_RATIO_BASE_SIZE_REPLICATED": (
        "size_ratio를 base size 복제로 처리했다.",
        "grading 차이는 추론하지 않으므로 사이즈별 실제 외곽선이 필요한 작업에는 부족하다.",
    ),
    "PIECE_QUANTITY_APPLIED": (
        "piece_quantity에 따라 피스가 복제됐다.",
        "좌우 대칭, 접힘 피스, 세트 구성은 현재 단순 수량 복제 기준이다.",
    ),
    "NAP_ROTATION_NOT_ALLOWED": (
        "원웨이 원단에서 180도 회전이 차단됐다.",
        "방향성이 없는 원단이면 nap_direction을 two_way로 바꿔 다시 계산한다.",
    ),
    "INVALID_CUTTABLE_WIDTH": (
        "cuttable_width가 fabric_width보다 크다.",
        "실제 재단 가능 폭은 전체 원단 폭보다 클 수 없다.",
    ),
}


def explain_message(code: str, message: str = "") -> dict[str, str]:
    title, action = MESSAGE_HELP.get(
        code,
        ("추가 설명이 없는 메시지다.", "원문 메시지를 보고 DXF, 원단 조건, 입력값을 확인한다."),
    )
    return {
        "code": code,
        "title": title,
        "action": action,
        "message": message,
    }


def build_advisor_state(result: dict[str, Any] | None = None, *, llm_available: bool = False) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    status = "ready"
    next_steps = [
        "DXF를 업로드하고 원단 폭을 입력한다.",
        "모르는 값은 기본값으로 시작한 뒤 preview와 warning을 확인한다.",
        "quote_yield는 견적용 값이고 생산 확정 요척이 아니다.",
    ]

    if result is not None:
        status = str(result.get("status", "unknown"))
        for item in [*(result.get("errors") or []), *(result.get("warnings") or [])]:
            messages.append(explain_message(str(item.get("code", "UNKNOWN")), str(item.get("message", ""))))
        if status == "completed":
            next_steps = [
                "marker_preview.svg에서 피스가 원단 폭 안에 제대로 배치됐는지 확인한다.",
                "Quote Summary에서 minimum_yield와 quote_yield 차이를 확인한다.",
                "PDF 또는 CSV를 공유하기 전에 warning을 해결하거나 메모로 남긴다.",
            ]
        elif status == "blocked":
            next_steps = [
                "blocker 설명을 먼저 해결한다.",
                "DXF export 방식, 식서선 layer, 원단 조건을 수정한 뒤 다시 계산한다.",
                "blocked 결과는 견적 요척으로 사용하지 않는다.",
            ]

    return {
        "status": status,
        "field_help": list(FIELD_HELP),
        "messages": messages,
        "next_steps": next_steps,
        "llm_available": llm_available,
    }
