#!/usr/bin/env python3
"""Regenerate the media probe fixtures in tests/fixtures/media/.

macOS only: uses `say`, `afconvert`, `sips` and `ffmpeg` (brew install ffmpeg).
Each fixture carries one marker that a model must repeat to prove it read the media:
  zebra.pdf   -> "ZEBRA-42"
  pelican.wav -> spoken "The code word is pelican seven."
  otter.mp4   -> frame text "OTTER-9"
"""

import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "media"


def _one_page_pdf(text: str, width: int, height: int, font_size: int, navy_background: bool) -> bytes:
    """Return a minimal valid single-page PDF showing `text` in Helvetica-Bold."""
    fill = b"0 0 0.5 rg 0 0 %d %d re f 1 1 1 rg " % (width, height) if navy_background else b""
    stream = fill + b"BT /F1 %d Tf 40 %d Td (%s) Tj ET" % (font_size, height // 2 - font_size // 3, text.encode())
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>" % (width, height),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "zebra.pdf").write_bytes(_one_page_pdf("ZEBRA-42", 300, 144, 24, navy_background=False))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        aiff = tmp_path / "pelican.aiff"
        subprocess.run(["say", "-o", str(aiff), "The code word is pelican seven."], check=True)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(OUT / "pelican.wav")], check=True
        )

        frame_pdf = tmp_path / "frame.pdf"
        frame_png = tmp_path / "frame.png"
        frame_pdf.write_bytes(_one_page_pdf("OTTER-9", 640, 360, 96, navy_background=True))
        subprocess.run(
            ["sips", "-s", "format", "png", str(frame_pdf), "--out", str(frame_png)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-loop",
                "1",
                "-i",
                str(frame_png),
                "-t",
                "3",
                "-r",
                "24",
                "-vf",
                "scale=640:360",
                "-pix_fmt",
                "yuv420p",
                "-c:v",
                "libx264",
                str(OUT / "otter.mp4"),
            ],
            check=True,
        )
    for name in ("zebra.pdf", "pelican.wav", "otter.mp4"):
        print(f"{name}: {(OUT / name).stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
