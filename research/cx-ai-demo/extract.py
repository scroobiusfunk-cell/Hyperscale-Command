#!/usr/bin/env python3
"""Unpack the CX-AI Commissioning Matrix demo artifact into analysable files.

The demo ships as one HTML file: a shell (router + iframe + toast) plus a single
<script type="application/json" id="cx-demo-data"> blob holding every page of the
app, pre-rendered. This script splits that blob back out into one file per page,
so the pages can be read, grepped and diffed with ordinary tools.

Usage:  python3 extract.py <demo.html> <output-dir>

Page bodies are written exactly as they are served, including the three
placeholder tokens the demo's router substitutes at render time:
    __CX_CSS__   -> assets/app.css
    __CX_LOGO__  -> assets/logo.png (a data: URI in the original)
    __CX_SHIM__  -> assets/shim.js  (wrapped in <script> tags)
"""
import base64
import hashlib
import json
import re
import sys
from pathlib import Path


def slugify(path: str) -> str:
    """Turn an app route into a filesystem-safe name that stays readable."""
    route, _, query = path.partition("?")
    params = dict(
        p.split("=", 1) for p in query.split("&") if "=" in p
    )
    project = params.get("project_id", "")
    name = route.strip("/").replace("/", "-") or "matrix"
    parts = [name]
    if project:
        parts.append(project)
    if "initial_limit" in params:
        parts.append(f"limit{params['initial_limit']}")
    return "__".join(parts) + ".html"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2

    src_path, out_root = Path(sys.argv[1]), Path(sys.argv[2])
    src = src_path.read_text(encoding="utf-8", errors="replace")

    marker = '<script type="application/json" id="cx-demo-data">'
    start = src.index(marker) + len(marker)
    end = src.index("</script>", start)
    data = json.loads(src[start:end])

    pages_dir = out_root / "pages"
    assets_dir = out_root / "assets"
    pages_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    # The shell, with the multi-megabyte data blob removed.
    shell = src[: src.index(marker)] + marker + "\n/* page data extracted to pages/ */\n" + src[end:]
    (out_root / "shell.html").write_text(shell, encoding="utf-8")

    (assets_dir / "app.css").write_text(data["assets"]["css"], encoding="utf-8")
    (assets_dir / "shim.js").write_text(data["shim"], encoding="utf-8")
    (assets_dir / "api.json").write_text(
        json.dumps(data["api"], indent=2), encoding="utf-8"
    )

    logo = data["assets"]["logo"]
    if logo.startswith("data:"):
        (assets_dir / "logo.png").write_bytes(
            base64.b64decode(logo.split(",", 1)[1])
        )

    manifest = {
        "source_file": src_path.name,
        "source_sha256": hashlib.sha256(src_path.read_bytes()).hexdigest(),
        "landing": data["landing"],
        "api_endpoints": sorted(data["api"]),
        "pages": [],
    }

    seen: dict[str, str] = {}
    for route, body in data["pages"].items():
        filename = slugify(route)
        if filename in seen:
            filename = filename.replace(".html", f"--{len(seen)}.html")
        seen[filename] = route
        (pages_dir / filename).write_text(body, encoding="utf-8")
        manifest["pages"].append(
            {"route": route, "file": f"pages/{filename}", "bytes": len(body)}
        )

    manifest["pages"].sort(key=lambda p: p["route"])
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"{len(manifest['pages'])} pages -> {pages_dir}")
    print(f"source sha256 {manifest['source_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
