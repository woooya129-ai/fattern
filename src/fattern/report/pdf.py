"""Minimal PDF report rendering for marker reports."""

from __future__ import annotations


def render_marker_pdf(report_text: str) -> bytes:
    """Render report text into a simple single-page PDF artifact."""

    lines = [_plain_pdf_line(line) for line in report_text.splitlines()[:54]]
    stream = "\n".join(
        (
            "BT",
            "/F1 10 Tf",
            "50 790 Td",
            "14 TL",
            *[f"({_escape_pdf_literal(line)}) Tj T*" for line in lines],
            "ET",
        )
    ).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    return _build_pdf(objects)


def _build_pdf(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _plain_pdf_line(value: str) -> str:
    text = value.replace("`", "").replace("*", "").replace("|", " ")
    return "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in text)[:110]


def _escape_pdf_literal(value: str) -> str:
    clean = value.encode("latin-1", errors="replace").decode("latin-1")
    return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
