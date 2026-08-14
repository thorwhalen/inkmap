"""The real-photograph test corpus: 384 photographed marks in the wild, from Wikimedia Commons.

189 QR codes, 56 linear barcodes and 139 images of printed text -- signs, posters,
packaging, business cards, stickers, billboards, menus, tickets, screens, inscriptions.

Synthetic scenes (:mod:`inkmap.synth`) are the only way to validate a *coverage* value,
because no photograph comes with per-pixel ink ground truth. But synthetic scenes cannot
tell you whether detection survives a mark printed on a curved bottle under a sodium
lamp. The two test sets answer different questions and you need both.

Only the manifest ships with the package -- titles, URLs, licences and attribution,
about 200 KB. The images are fetched on demand and cached, because a few hundred MB of
photographs has no business inside a wheel, and because redistributing them would mean
carrying every attribution requirement into this repository.

Every image is CC0, public domain, CC BY or CC BY-SA. Attribution is in the manifest and
:func:`attribution_text` will render it -- if you publish results using these images,
use it.

    from inkmap import corpus

    corpus.kinds()                          # {'qr': 189, 'barcode': 56, 'text': 139}
    paths = corpus.fetch(kind="barcode")    # download + cache, returns local paths
    for path, meta in corpus.items(kind="qr"):
        ...
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

__all__ = ["MANIFEST", "kinds", "cache_dir", "fetch", "items", "attribution_text"]

_MANIFEST_PATH = Path(__file__).parent / "data" / "commons_marks.json"
_USER_AGENT = "inkmap/0.1 (https://github.com/thorwhalen/inkmap)"

#: Manifest records: kind (qr/barcode/text), file, title, url, source, license, artist.
MANIFEST: list[dict] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def cache_dir() -> Path:
    """Where fetched images live.

    Honours ``INKMAP_CORPUS_DIR``, else the XDG cache location. Test data is neither code
    nor user configuration, so it does not belong beside the package: a wheel install
    would make the package directory read-only, and a reinstall would silently discard
    a 120 MB download.
    """
    env = os.environ.get("INKMAP_CORPUS_DIR")
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base).expanduser() / "inkmap" / "commons_marks"


def kinds() -> dict[str, int]:
    """How many records of each mark kind the manifest holds."""
    counts: dict[str, int] = {}
    for record in MANIFEST:
        counts[record["kind"]] = counts.get(record["kind"], 0) + 1
    return counts


def fetch(
    *,
    kind: str | None = None,
    limit: int | None = None,
    dest: Path | None = None,
    pace: float = 1.1,
    attempts: int = 5,
) -> list[Path]:
    """Download the corpus (skipping anything already cached) and return local paths.

    Commons rate-limits hard and answers with HTTP 429 rather than queueing, so
    requests are paced and retried with exponential backoff. A full cold fetch takes
    several minutes; it is incremental, so interrupting and re-running is safe.
    """
    dest = Path(dest) if dest else cache_dir()
    dest.mkdir(parents=True, exist_ok=True)

    records = [r for r in MANIFEST if kind is None or r["kind"] == kind]
    paths: list[Path] = []
    for record in records[:limit]:
        target = dest / record["file"]
        if target.exists() and target.stat().st_size > 0:
            paths.append(target)
            continue
        if _download(record["url"], target, pace=pace, attempts=attempts):
            paths.append(target)
    return paths


def _download(url: str, dest: Path, *, pace: float, attempts: int) -> bool:
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                dest.write_bytes(response.read())
            time.sleep(pace)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code != 429:
                return False
            time.sleep(pace * (2**attempt) * 4)
        except Exception:
            time.sleep(pace * 2)
    return False


def items(
    *, kind: str | None = None, dest: Path | None = None
) -> Iterator[tuple[Path, dict]]:
    """Yield ``(path, record)`` for every cached corpus image, optionally by kind."""
    dest = Path(dest) if dest else cache_dir()
    for record in MANIFEST:
        if kind is not None and record["kind"] != kind:
            continue
        path = dest / record["file"]
        if path.exists():
            yield path, record


def attribution_text(records: list[dict] | None = None) -> str:
    """Render the attribution block required by the CC BY / CC BY-SA images."""
    records = MANIFEST if records is None else records
    lines = [
        "Test images from Wikimedia Commons, used under their respective licences:",
        "",
    ]
    for record in records:
        title = record["title"].removeprefix("File:")
        artist = record.get("artist") or "unknown"
        lines.append(
            f"- {title} -- {artist} -- {record['license']} -- {record['source']}"
        )
    return "\n".join(lines)
