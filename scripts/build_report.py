"""Render docs/methods-and-results.md to a self-contained PDF.

Markdown is the source of truth -- it renders on GitHub, greps, and diffs. The PDF is a
derived artefact for people who want one document to read or circulate.

Prefers pandoc (best typography, handles the tables well); falls back to
markdown + weasyprint, which needs no external binary.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "methods-and-results.md"
TARGET = ROOT / "docs" / "methods-and-results.pdf"

CSS = """
@page { size: A4; margin: 20mm 18mm; @bottom-center { content: counter(page); font-size: 9pt; color: #888; } }
body { font-family: "Charter", "Georgia", serif; font-size: 10.5pt; line-height: 1.5; color: #1a1a1a; }
h1 { font-size: 22pt; border-bottom: 2px solid #333; padding-bottom: 6px; }
h2 { font-size: 15pt; margin-top: 1.6em; border-bottom: 1px solid #ccc; padding-bottom: 3px; }
h3 { font-size: 12pt; margin-top: 1.2em; }
code, pre { font-family: "SF Mono", "Menlo", monospace; font-size: 8.8pt; }
pre { background: #f6f6f4; padding: 8px 10px; border-radius: 4px; border-left: 3px solid #ccc;
      white-space: pre-wrap; word-wrap: break-word; }
code { background: #f0f0ee; padding: 1px 3px; border-radius: 3px; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 9pt; }
th, td { border: 1px solid #d0d0d0; padding: 4px 7px; text-align: left; }
th { background: #efefec; font-weight: 600; }
tr:nth-child(even) td { background: #fafaf8; }
blockquote { border-left: 3px solid #bbb; margin-left: 0; padding-left: 12px; color: #444; }
img { max-width: 100%; }
"""


def with_pandoc() -> bool:
    if not shutil.which("pandoc"):
        return False
    css = ROOT / "docs" / "_report.css"
    css.write_text(CSS)
    for engine in ("weasyprint", "wkhtmltopdf"):
        if not shutil.which(engine):
            continue
        cmd = [
            "pandoc",
            str(SOURCE),
            "-o",
            str(TARGET),
            f"--pdf-engine={engine}",
            "--css",
            str(css),
            "--standalone",
            "--toc",
            "--toc-depth=2",
            "--metadata",
            "title=inkmap — methods and results",
        ]
        if subprocess.run(cmd, capture_output=True).returncode == 0:
            css.unlink(missing_ok=True)
            return True
    css.unlink(missing_ok=True)
    return False


def with_weasyprint() -> bool:
    try:
        import markdown
        from weasyprint import CSS as WCSS, HTML
    except ImportError:
        return False
    html = markdown.markdown(
        SOURCE.read_text(), extensions=["tables", "fenced_code", "toc", "attr_list"]
    )
    HTML(string=f"<html><body>{html}</body></html>", base_url=str(ROOT)).write_pdf(
        TARGET, stylesheets=[WCSS(string=CSS)]
    )
    return True


if __name__ == "__main__":
    if not SOURCE.exists():
        sys.exit(f"missing {SOURCE}")
    if with_pandoc() or with_weasyprint():
        size = TARGET.stat().st_size / 1024
        print(f"wrote {TARGET} ({size:.0f} KB)")
    else:
        sys.exit("no PDF engine available: install pandoc+weasyprint, or weasyprint")
