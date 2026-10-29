"""
wikikit/lookup.py - Titles, QIDs and sitelinks, batched and memoized.

The heart of language-independent link mapping: a link in the source
article points at a page; that page has a Wikidata item; the item has a
sitelink on the target wiki (or not). One `action=query` request per 50
titles answers redirect + QID + target-language title together, so a
typical article costs two or three requests.

An API failure is never cached as "absent": those titles land in
`Lookup.failed` and are reported, so a network hiccup does not silently
turn a blue link red.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from wikikit.api import BATCH_DELAY, BATCH_SIZE, api

_ABSENT = object()   # cached "looked up and not found"


@dataclass
class PageInfo:
    title: str                      # as asked
    resolved: str                   # after normalisation + redirects
    qid: Optional[str]
    target_title: Optional[str]     # sitelink on the target wiki
    exists: bool = True
    length: Optional[int] = None    # bytes, when requested

    def as_dict(self) -> dict:
        return {
            "resolved": self.resolved, "qid": self.qid,
            "target_title": self.target_title, "exists": self.exists,
            "length": self.length,
        }


@dataclass
class Lookup:
    """Per-job memo of page info and sitelinks between a source and target wiki."""

    source: str = "en"                  # site spec of the source wiki
    target_lang: str = "uz"             # language of the target wiki
    family: str = "wikipedia"
    pages: Dict[str, PageInfo] = field(default_factory=dict)
    sitelinks: Dict[str, object] = field(default_factory=dict)   # "Q1:uzwiki" -> title | _ABSENT
    failed: set = field(default_factory=set)

    @property
    def target_site_id(self) -> str:
        """Wikidata site id: uzwiki, uzwiktionary, ..."""
        suffix = "wiki" if self.family == "wikipedia" else self.family
        return f"{self.target_lang.replace('-', '_')}{suffix}"

    def page_info(self, titles: Iterable[str], with_length: bool = False) -> Dict[str, PageInfo]:
        """Redirect target, QID and target-wiki title for every title, batched."""
        wanted = list(dict.fromkeys(t for t in titles if t and t.strip()))
        todo = [t for t in wanted if t not in self.pages]
        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i:i + BATCH_SIZE]
            if i:
                time.sleep(BATCH_DELAY)
            props = "pageprops|langlinks" + ("|info" if with_length else "")
            try:
                data = api({
                    "action": "query", "titles": "|".join(batch), "redirects": "1",
                    "prop": props, "ppprop": "wikibase_item",
                    "lllang": self.target_lang, "lllimit": "max",
                }, site=self.source)
            except Exception:
                self.failed.update(batch)
                continue
            q = data.get("query", {})
            norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
            redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
            by_title = {p["title"]: p for p in q.get("pages", [])}
            for t in batch:
                n = norm.get(t, t)
                resolved = redir.get(n, n)
                pg = by_title.get(resolved, {})
                qid = pg.get("pageprops", {}).get("wikibase_item")
                ll = pg.get("langlinks") or []
                target = ll[0]["title"] if ll else None
                info = PageInfo(t, resolved, qid, target,
                                exists=bool(pg) and not pg.get("missing", False),
                                length=pg.get("length"))
                self.pages[t] = info
                if qid:
                    self.sitelinks[f"{qid}:{self.target_site_id}"] = target or _ABSENT
                self.failed.discard(t)
        return {t: self.pages[t] for t in wanted if t in self.pages}

    def sitelinks_for(self, qids: Iterable[str], site_id: Optional[str] = None) -> Dict[str, Optional[str]]:
        """QID -> title on `site_id` (default: the target wiki), batched over Wikidata."""
        site_id = site_id or self.target_site_id
        wanted = list(dict.fromkeys(q for q in qids if q))
        todo = [q for q in wanted if f"{q}:{site_id}" not in self.sitelinks]
        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i:i + BATCH_SIZE]
            try:
                data = api({"action": "wbgetentities", "ids": "|".join(batch),
                            "props": "sitelinks", "sitefilter": site_id}, site="wikidata")
            except Exception:
                self.failed.update(batch)
                continue
            ents = data.get("entities", {})
            for q in batch:
                sl = ents.get(q, {}).get("sitelinks", {}).get(site_id)
                self.sitelinks[f"{q}:{site_id}"] = sl["title"] if sl else _ABSENT
        out: Dict[str, Optional[str]] = {}
        for q in wanted:
            v = self.sitelinks.get(f"{q}:{site_id}")
            out[q] = None if v is _ABSENT or v is None else v  # type: ignore[assignment]
        return out

    def sitelink(self, qid: str, site_id: Optional[str] = None) -> Optional[str]:
        return self.sitelinks_for([qid], site_id).get(qid)

    def to_state(self) -> dict:
        """Serialisable snapshot, so finalize() in a later process skips the network."""
        return {
            "pages": {t: p.as_dict() for t, p in self.pages.items()},
            "sitelinks": {k: (None if v is _ABSENT else v) for k, v in self.sitelinks.items()},
            "failed": sorted(self.failed),
        }

    @classmethod
    def from_state(cls, state: dict, source: str, target_lang: str, family: str = "wikipedia") -> "Lookup":
        lk = cls(source=source, target_lang=target_lang, family=family)
        for t, d in state.get("pages", {}).items():
            lk.pages[t] = PageInfo(t, d["resolved"], d["qid"], d["target_title"],
                                   d.get("exists", True), d.get("length"))
        for k, v in state.get("sitelinks", {}).items():
            lk.sitelinks[k] = _ABSENT if v is None else v
        lk.failed = set(state.get("failed", []))
        return lk


def siteinfo(site: str) -> dict:
    """Namespaces (with aliases) and the wiki's language of `site`."""
    data = api({"action": "query", "meta": "siteinfo",
                "siprop": "general|namespaces|namespacealiases"}, site=site)
    q = data.get("query", {})
    ns = {str(v["id"]): v.get("name", "") for v in q.get("namespaces", {}).values()}
    aliases: Dict[str, List[str]] = {}
    for a in q.get("namespacealiases", []):
        aliases.setdefault(str(a["id"]), []).append(a["alias"])
    g = q.get("general", {})
    return {"sitename": g.get("sitename"), "lang": g.get("lang"),
            "namespaces": ns, "aliases": aliases}
