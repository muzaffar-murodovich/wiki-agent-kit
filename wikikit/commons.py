"""
wikikit/commons.py - Finding freely licensed media on Wikimedia Commons.

A translated article usually lacks the source's images only because nobody
checked. These helpers return what an editor needs to decide: the file, its
licence, its author, and whether it is already used on the item.
"""

from __future__ import annotations

import re
from typing import Dict, List

from wikikit.api import api


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def file_info(files: List[str]) -> Dict[str, dict]:
    titles = [f if f.lower().startswith(("file:", "image:")) else f"File:{f}" for f in files][:50]
    data = api({"action": "query", "titles": "|".join(titles), "prop": "imageinfo",
                "iiprop": "url|size|extmetadata", "iiurlwidth": "400"}, site="commons")
    out = {}
    for p in data.get("query", {}).get("pages", []):
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        g = lambda k: _clean(md.get(k, {}).get("value", ""))
        out[p["title"]] = {
            "exists": not p.get("missing"),
            "license": g("LicenseShortName"), "license_url": g("LicenseUrl"),
            "author": g("Artist"), "credit": g("Credit"),
            "description": g("ImageDescription")[:300], "date": g("DateTimeOriginal"),
            "thumb": ii.get("thumburl"), "page": ii.get("descriptionurl"),
            "width": ii.get("width"), "height": ii.get("height"),
        }
    return out


def search(query: str, limit: int = 10) -> List[dict]:
    data = api({"action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap|drawing {query}",
                "gsrnamespace": "6", "gsrlimit": str(min(limit, 50)), "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": "300"}, site="commons")
    out = []
    for p in sorted(data.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        out.append({"file": p["title"], "license": _clean(md.get("LicenseShortName", {}).get("value", "")),
                    "author": _clean(md.get("Artist", {}).get("value", ""))[:80], "thumb": ii.get("thumburl")})
    return out


def images_in_article(title: str, site: str = "en") -> List[str]:
    """Files used in an article (e.g. the source of a translation)."""
    data = api({"action": "query", "titles": title, "prop": "images", "imlimit": "max", "redirects": "1"}, site=site)
    pages = data.get("query", {}).get("pages", [])
    files = [i["title"] for i in (pages[0].get("images", []) if pages else [])]
    # Interface icons are not content.
    return [f for f in files if not re.search(r"(?i)(icon|symbol|logo|flag of|commons-logo|wiki.*\.svg|edit-clear|question_book)", f)]
