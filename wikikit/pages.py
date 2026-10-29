"""
wikikit/pages.py - Reading pages: wikitext, revisions, links, existence.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Dict, Iterable, List, Optional, Tuple

from wikikit.api import BATCH_SIZE, api, site_host

_URL = re.compile(r"https?://([a-z0-9.-]+\.org)/(?:wiki/([^?#]+)|w/index\.php\?(.*))", re.I)


def parse_page_ref(ref: str, default_site: str = "en") -> Tuple[str, str]:
    """
    "https://en.wikipedia.org/wiki/Al-Biruni" -> ("en.wikipedia.org", "Al-Biruni")
    "Al-Biruni"                                -> (default_site, "Al-Biruni")
    "uz:Beruniy"                               -> ("uz", "Beruniy") for a 2-3 letter prefix
    """
    ref = ref.strip()
    m = _URL.match(ref)
    if m:
        host, path, query = m.groups()
        host = host.replace(".m.", ".")   # en.m.wikipedia.org -> en.wikipedia.org
        if path:
            title = urllib.parse.unquote(path)
        else:
            title = urllib.parse.parse_qs(query or "").get("title", [""])[0]
        return host, title.replace("_", " ")
    pre = re.match(r"^([a-z]{2,3}(?:-[a-z]+)?):(.+)$", ref)
    if pre:
        return pre.group(1), pre.group(2).strip()
    return default_site, ref.replace("_", " ")


def fetch_wikitext(title: str, site: str = "en") -> Dict[str, object]:
    """Current wikitext of a page, following redirects. Raises LookupError when missing."""
    data = api({"action": "query", "prop": "revisions|pageprops", "titles": title,
                "redirects": "1", "rvprop": "content|ids|timestamp", "rvslots": "main",
                "ppprop": "wikibase_item"}, site=site)
    q = data.get("query", {})
    pages = q.get("pages", [])
    if not pages or pages[0].get("missing") or pages[0].get("invalid"):
        raise LookupError(f"Page not found on {site_host(site)}: {title}")
    pg = pages[0]
    rev = pg["revisions"][0]
    redirects = q.get("redirects", [])
    return {
        "title": pg["title"],
        "redirected_from": redirects[0]["from"] if redirects else None,
        "revid": rev.get("revid"),
        "timestamp": rev.get("timestamp"),
        "qid": pg.get("pageprops", {}).get("wikibase_item"),
        "wikitext": rev["slots"]["main"]["content"],
        "site": site_host(site),
    }


def exists(titles: Iterable[str], site: str) -> Dict[str, bool]:
    """Which titles exist on `site` (redirects count as existing)."""
    titles = list(dict.fromkeys(t for t in titles if t))
    out: Dict[str, bool] = {}
    for i in range(0, len(titles), BATCH_SIZE):
        batch = titles[i:i + BATCH_SIZE]
        data = api({"action": "query", "titles": "|".join(batch)}, site=site)
        q = data.get("query", {})
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        state = {p["title"]: not (p.get("missing") or p.get("invalid")) for p in q.get("pages", [])}
        for t in batch:
            out[t] = state.get(norm.get(t, t), False)
    return out


def search(query: str, site: str = "en", limit: int = 10) -> List[dict]:
    data = api({"action": "query", "list": "search", "srsearch": query,
                "srlimit": str(min(limit, 50)), "srprop": "size|snippet"}, site=site)
    return [{"title": r["title"], "size": r.get("size"),
             "snippet": re.sub(r"<[^>]+>", "", r.get("snippet", ""))}
            for r in data.get("query", {}).get("search", [])]


def langlinks(title: str, site: str = "en") -> Dict[str, str]:
    """{lang: title} of every other-language version of a page."""
    data = api({"action": "query", "prop": "langlinks", "titles": title,
                "redirects": "1", "lllimit": "max"}, site=site)
    pages = data.get("query", {}).get("pages", [])
    return {ll["lang"]: ll["title"] for ll in (pages[0].get("langlinks", []) if pages else [])}


def page_categories(titles: Iterable[str], site: str = "en", hidden: bool = False) -> Dict[str, List[str]]:
    """Categories of each page (without the namespace prefix), hidden ones excluded by default."""
    titles = list(dict.fromkeys(titles))
    out: Dict[str, List[str]] = {t: [] for t in titles}
    for i in range(0, len(titles), BATCH_SIZE):
        batch = titles[i:i + BATCH_SIZE]
        params = {"action": "query", "prop": "categories", "titles": "|".join(batch),
                  "redirects": "1", "cllimit": "max"}
        if not hidden:
            params["clshow"] = "!hidden"
        cont: Dict[str, str] = {}
        while True:
            data = api({**params, **cont}, site=site)
            q = data.get("query", {})
            back = {}
            for n in q.get("normalized", []):
                back[n["to"]] = n["from"]
            for r in q.get("redirects", []):
                back[r["to"]] = back.get(r["from"], r["from"])
            for p in q.get("pages", []):
                key = back.get(p["title"], p["title"])
                for c in p.get("categories", []):
                    out.setdefault(key, []).append(c["title"].split(":", 1)[-1])
            if "continue" not in data:
                break
            cont = data["continue"]
    return out
