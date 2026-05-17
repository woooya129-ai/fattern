"""Shared schema contract constants.

These constants mirror `.agents/queue/policy-lock.md` and are intentionally
small so P2 and P3 can import policy values without asking an LLM to infer them.
"""

DEFAULT_UNIT = "cm"
DEFAULT_ROTATION_ALLOWED_DEGREES = (0,)
DEFAULT_CLEARANCE_CM = 0.2
RECOMMENDED_YIELD_CEIL_UNIT_CM = 10
SUPPORTED_UNITS = ("mm", "cm", "m", "inch", "ft", "yd")

ID_PATTERN = r"^(job|file|dxf_parse|piece_set|metrics|layout|artifact)_[a-z0-9_-]{1,72}$"
