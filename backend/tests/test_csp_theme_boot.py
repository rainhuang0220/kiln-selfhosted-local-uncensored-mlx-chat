"""CSP: built index must not ship inline scripts without a matching hash."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "web" / "index.html"
DIST_INDEX = ROOT / "web" / "dist" / "index.html"
NGINX = ROOT / "deploy" / "nginx-security-headers.conf"
CADDY = ROOT / "deploy" / "Caddyfile"
THEME_BOOT = ROOT / "web" / "public" / "theme-boot.js"


_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)


def test_source_index_uses_external_theme_boot():
    html = INDEX.read_text(encoding="utf-8")
    assert 'src="/theme-boot.js"' in html
    assert THEME_BOOT.is_file()
    assert not _INLINE_SCRIPT.search(html)


def test_csp_configs_forbid_unsafe_inline_scripts():
    nginx = NGINX.read_text(encoding="utf-8")
    caddy = CADDY.read_text(encoding="utf-8")
    assert "script-src 'self'" in nginx
    assert "unsafe-inline" not in nginx.split("script-src")[1].split(";")[0]
    assert "script-src 'self'" in caddy
    assert "unsafe-inline" not in caddy.split("script-src")[1].split(";")[0]


def test_dist_index_has_no_inline_script_if_present():
    if not DIST_INDEX.is_file():
        return
    html = DIST_INDEX.read_text(encoding="utf-8")
    # Allow module scripts with src=; ban bare inline blocks.
    for match in _INLINE_SCRIPT.finditer(html):
        # type=module with src is fine — regex already excludes src=
        raise AssertionError(f"inline script found in dist index: {match.group(0)}")
