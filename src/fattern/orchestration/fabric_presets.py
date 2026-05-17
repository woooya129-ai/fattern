"""Questionnaire presets for rough marker setup."""

from __future__ import annotations

FABRIC_WIDTH_PRESETS = (
    {
        "id": "apparel_44_45",
        "label": "44-45 in / 112-115 cm",
        "width_cm": 114.0,
        "use_case": "basic apparel, quilting cotton, crafts",
    },
    {
        "id": "apparel_home_54",
        "label": "54 in / 137 cm",
        "width_cm": 137.0,
        "use_case": "many apparel, upholstery, home decor fabrics",
    },
    {
        "id": "wide_apparel_58_60",
        "label": "58-60 in / 147-152 cm",
        "width_cm": 150.0,
        "use_case": "wide apparel, knits, dresses, coats",
    },
    {
        "id": "wideback_108",
        "label": "108 in / 274 cm",
        "width_cm": 274.0,
        "use_case": "quilt backing, bedding, large panels",
    },
    {
        "id": "drapery_118",
        "label": "118 in / 300 cm",
        "width_cm": 300.0,
        "use_case": "extra-wide drapery and sheer fabrics",
    },
)

QUESTIONNAIRE_FIELDS = (
    "dxf_file",
    "fabric_width",
    "unit",
    "dxf_unit_hint",
    "seam_allowance_included",
    "seam_allowance_width",
    "one_way_fabric",
    "rotation_allowed_degrees",
    "clearance",
)


def fabric_width_allowed_answers() -> list[str]:
    answers = [
        f"{preset['label']}: {preset['use_case']}"
        for preset in FABRIC_WIDTH_PRESETS
    ]
    answers.append("custom: 직접 숫자 입력")
    return answers
