"""
wikikit/finder.py - Which articles does the target wiki still lack?

Ported from wikipedia-translator's finder (which filled a daily queue of
English articles missing from Uzbek Wikipedia), generalised to any source
and target language. Two ways in:

  * a category: every member of a source-wiki category, with its size and
    whether the target wiki has it — one request per 500 members;
  * a page's links: the articles an existing page links to, so a freshly
    translated article's red links become the next worklist.

Screening is evidence, not a verdict. `evidence()` returns each candidate's
own topical categories and the agent (and the human) decide. A keyword list
cannot tell "Wahhabis" from "Critics of Wahhabism"; the earlier version that
tried kept buying the next false positive.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from wikikit import profiles
from wikikit.api import BATCH_SIZE, api, site_host
from wikikit.pages import page_categories

DEFAULT_MAINTENANCE = (
    r"(?i)^(?:All |Articles |Pages |Wikipedia |CS1 |Webarchive|Use \w+ dates"
    r"|Commons category|Short description|Harv and Sfn|Interlanguage link)"
    r"|\bstubs?$|^\d+s? (?:births|deaths)$|^\d+(?:st|nd|rd|th)-century (?:births|deaths)$"
    r"|^(?:Year of|Date of|Place of) (?:birth|death)"
)


def _cat(name: str) -> str:
    return name.split(":", 1)[1] if name.lower().startswith("category:") else name


def maintenance_re(source_lang: str) -> re.Pattern:
    return re.compile(profiles.load(source_lang).source_setting("maintenance_category", DEFAULT_MAINTENANCE))


def category_members(category: str, target_lang: str, source: str = "en") -> Dict[str, dict]:
    """{title: {"target": title|None, "size": bytes}} for every article in a category."""
    params = {"action": "query", "generator": "categorymembers",
              "gcmtitle": "Category:" + _cat(category), "gcmlimit": "500",
              "gcmnamespace": "0", "gcmtype": "page", "prop": "langlinks|info",
              "lllang": target_lang, "lllimit": "max"}
    out: Dict[str, dict] = {}
    cont: Dict[str, str] = {}
    while True:
        data = api({**params, **cont}, site=source)
        for p in data.get("query", {}).get("pages", []):
            rec = out.setdefault(p["title"], {"target": None, "size": 0})
            ll = p.get("langlinks") or []
            rec["target"] = rec["target"] or (ll[0]["title"] if ll else None)
            rec["size"] = rec["size"] or p.get("length", 0)
        if "continue" not in data:
            break
        cont = data["continue"]
    return out


def linked_articles(page: str, target_lang: str, source: str = "en") -> Dict[str, dict]:
    """Articles that `page` links to, with their target-wiki title (or None)."""
    params = {"action": "query", "generator": "links", "titles": page, "redirects": "1",
              "gplnamespace": "0", "gpllimit": "max", "prop": "langlinks|info",
              "lllang": target_lang, "lllimit": "max"}
    out: Dict[str, dict] = {}
    cont: Dict[str, str] = {}
    while True:
        data = api({**params, **cont}, site=source)
        for p in data.get("query", {}).get("pages", []):
            if p.get("missing"):
                continue
            rec = out.setdefault(p["title"], {"target": None, "size": 0})
            ll = p.get("langlinks") or []
            rec["target"] = rec["target"] or (ll[0]["title"] if ll else None)
            rec["size"] = rec["size"] or p.get("length", 0)
        if "continue" not in data:
            break
        cont = data["continue"]
    return out


def subcategories(category: str, source: str = "en") -> List[str]:
    data = api({"action": "query", "list": "categorymembers", "cmtitle": "Category:" + _cat(category),
                "cmtype": "subcat", "cmlimit": "max"}, site=source)
    return [_cat(m["title"]) for m in data.get("query", {}).get("categorymembers", [])]


def parent_categories(category: str, source: str = "en") -> List[str]:
    return page_categories(["Category:" + _cat(category)], source).get("Category:" + _cat(category), [])


def evidence(titles: Iterable[str], source: str = "en") -> Dict[str, List[str]]:
    """Each article's topical categories — what the agent screens on."""
    maint = maintenance_re(source.split(".")[0])
    cats = page_categories(list(titles), source)
    return {t: [c for c in cs if not maint.search(c)] for t, cs in cats.items()}


def pageviews(titles: Iterable[str], source: str = "en", days: int = 30) -> Dict[str, Optional[int]]:
    """Total views over the last `days` days (one REST call per title; use on short lists)."""
    from wikikit.api import _SSL, _throttle, user_agent  # local: only this function needs raw REST
    import urllib.request
    end = _dt.date.today() - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=days - 1)
    project = site_host(source).replace(".org", "")
    out: Dict[str, Optional[int]] = {}
    for t in list(titles)[:60]:
        art = urllib.parse.quote(t.replace(" ", "_"), safe="")
        url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/all-access/user/"
               f"{art}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
            _throttle()
            with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
                items = json.loads(r.read().decode()).get("items", [])
            out[t] = sum(i.get("views", 0) for i in items)
        except Exception:
            out[t] = None
    return out


# ----------------------------------------------------------------- queue

STATUS_RANK = {"queued": 1, "translated": 2, "published": 3}


class Queue:
    """
    A worklist per language pair, in $WIKIKIT_HOME/queue.<src>-<tgt>.json.

    Rules carried over from wikipedia-translator, each learned the hard way:
      * a status never goes down (a published article met again in another
        category does not fall back to "queued");
      * a rejection always carries a reason, so "why was X left out?" has an
        answer weeks later;
      * articles that already exist on the target wiki are not stored — they
        are most of every category and would bloat the file;
      * writes are atomic (os.replace).
    """

    def __init__(self, source_lang: str, target_lang: str, path: Optional[Path] = None):
        self.path = path or profiles.home() / f"queue.{source_lang}-{target_lang}.json"
        self.data = {"articles": {}, "categories": {}}
        if self.path.is_file():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            self.data.setdefault("articles", {})
            self.data.setdefault("categories", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def _now() -> str:
        return _dt.datetime.now().isoformat(timespec="seconds")

    def known(self, title: str) -> Optional[str]:
        a = self.data["articles"].get(title)
        return a["status"] if a else None

    def add(self, title: str, size: int = 0, category: str = "", note: str = "") -> str:
        a = self.data["articles"].get(title)
        if a and a["status"] != "rejected":
            return f"dup:{a['status']}"
        if a and a["status"] == "rejected":
            return "dup:rejected"
        self.data["articles"][title] = {"status": "queued", "size": size, "category": category,
                                        "note": note, "added": self._now()}
        return "added"

    def set_status(self, title: str, status: str) -> str:
        a = self.data["articles"].get(title)
        if not a:
            return "unknown"
        if status not in STATUS_RANK:
            return f"invalid status {status!r}: use reject() for rejections"
        if STATUS_RANK.get(status, 0) > STATUS_RANK.get(a["status"], 0):
            a["status"] = status
            a[f"{status}_at"] = self._now()
            return "ok"
        return f"kept:{a['status']}"

    def reject(self, title: str, reason: str, category: str = "") -> str:
        if not reason.strip():
            raise ValueError("A rejection needs a reason.")
        a = self.data["articles"].get(title)
        if a and a["status"] in ("translated", "published"):
            return f"kept:{a['status']}"   # left the queue: the human's to undo
        was = a["status"] if a else None
        self.data["articles"][title] = {**(a or {}), "status": "rejected", "reason": reason,
                                        "category": category or (a or {}).get("category", ""),
                                        "rejected_at": self._now()}
        return f"rejected (was {was})" if was else "rejected"

    def requeue(self, title: str) -> str:
        a = self.data["articles"].get(title)
        if not a or a["status"] != "rejected":
            return "not rejected"
        a["status"] = "queued"
        a.pop("reason", None)
        return "queued"

    def mark_category(self, category: str, status: str, **extra) -> None:
        c = self.data["categories"].setdefault(_cat(category), {})
        c.update({"status": status, "updated": self._now(), **extra})

    def category_status(self, category: str) -> Optional[str]:
        c = self.data["categories"].get(_cat(category))
        return c["status"] if c else None

    def next(self, n: int = 8) -> List[dict]:
        """Smallest queued articles first: the cheapest to translate and review."""
        q = [{"title": t, **a} for t, a in self.data["articles"].items() if a["status"] == "queued"]
        return sorted(q, key=lambda a: a.get("size") or 0)[:n]

    def rejected(self, contains: str = "", category: str = "") -> List[dict]:
        out = [{"title": t, **a} for t, a in self.data["articles"].items() if a["status"] == "rejected"
               and contains.lower() in a.get("reason", "").lower()
               and category.lower() in a.get("category", "").lower()]
        return sorted(out, key=lambda a: a.get("rejected_at", ""), reverse=True)

    def status(self) -> dict:
        counts: Dict[str, int] = {}
        for a in self.data["articles"].values():
            counts[a["status"]] = counts.get(a["status"], 0) + 1
        cats: Dict[str, int] = {}
        for c in self.data["categories"].values():
            cats[c["status"]] = cats.get(c["status"], 0) + 1
        return {"file": str(self.path), "articles": counts, "categories": cats}


def list_missing(category: str, target_lang: str, source: str = "en", limit: int = 40,
                 queue: Optional[Queue] = None, trim_threshold: int = 10000) -> dict:
    """Category members missing from the target wiki and not yet seen, smallest first."""
    members = category_members(category, target_lang, source)
    missing = {t: r for t, r in members.items() if not r["target"]}
    fresh = {t: r for t, r in missing.items() if not (queue and queue.known(t))}
    rows = sorted(fresh.items(), key=lambda kv: kv[1]["size"])
    shown = rows[:limit]
    if queue is not None:
        queue.mark_category(category, "exhausted" if len(rows) <= limit else "open",
                            members=len(members), missing=len(missing))
        queue.save()
    return {
        "category": _cat(category), "members": len(members), "missing": len(missing),
        "already_seen": len(missing) - len(fresh), "more": max(0, len(rows) - limit),
        "articles": [{"title": t, "size": r["size"], "mode": "trim" if r["size"] > trim_threshold else "full"}
                     for t, r in shown],
    }
