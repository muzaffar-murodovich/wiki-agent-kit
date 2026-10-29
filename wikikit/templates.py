"""
wikikit/templates.py - Porting a template (or Lua module) to another wiki.

Small wikis lose hours to this: an infobox depends on four other templates
and two modules, some of which exist locally under another name, some not at
all. port_plan() answers, in one call:

  * every template and module the page transcludes, recursively;
  * which of them already exist on the target wiki (via Wikidata / langlinks)
    and under what name;
  * the TemplateData parameter list, so labels can be translated;
  * the order to create the missing ones in (leaves first).

The agent then drafts localized copies into files; a human creates the pages.
"""

from __future__ import annotations

import json
from typing import Dict, List

from wikikit.api import api
from wikikit.lookup import Lookup
from wikikit.pages import fetch_wikitext


def _ns_name(title: str) -> str:
    return title if ":" in title else f"Template:{title}"


def dependencies(title: str, source: str = "en") -> List[str]:
    """Templates and modules a page transcludes (MediaWiki already resolves recursion)."""
    out: List[str] = []
    params = {"action": "query", "titles": _ns_name(title), "prop": "templates",
              "tlnamespace": "10|828", "tllimit": "max"}
    cont: Dict[str, str] = {}
    while True:
        data = api({**params, **cont}, site=source)
        for p in data.get("query", {}).get("pages", []):
            out += [t["title"] for t in p.get("templates", [])]
        if "continue" not in data:
            break
        cont = data["continue"]
    return sorted(set(out) - {_ns_name(title)})


def templatedata(title: str, source: str = "en", lang: str = "en") -> dict:
    data = api({"action": "templatedata", "titles": _ns_name(title), "lang": lang, "redirects": "1"}, site=source)
    pages = data.get("pages", {})
    if not pages:
        return {}
    td = next(iter(pages.values()))
    params = td.get("params", {}) or {}
    desc = td.get("description")
    return {
        "description": desc.get(lang) or desc.get("en") if isinstance(desc, dict) else desc,
        "params": {k: {"label": (v.get("label") or {}).get("en") if isinstance(v.get("label"), dict) else v.get("label"),
                       "type": v.get("type"), "required": v.get("required", False),
                       "aliases": v.get("aliases", [])} for k, v in params.items()},
        "order": td.get("paramOrder") or list(params),
    }


def port_plan(title: str, target_lang: str, source: str = "en") -> dict:
    """What it takes to bring `title` (and everything it needs) to the target wiki."""
    root = _ns_name(title)
    deps = dependencies(root, source)
    lk = Lookup(source=source, target_lang=target_lang)
    info = lk.page_info([root] + deps)
    sizes = {}
    data = api({"action": "query", "titles": "|".join(([root] + deps)[:50]), "prop": "info"}, site=source)
    for p in data.get("query", {}).get("pages", []):
        sizes[p["title"]] = p.get("length")
    rows = []
    for t in [root] + deps:
        i = info.get(t)
        rows.append({"source": t, "target": i.target_title if i else None,
                     "qid": i.qid if i else None, "bytes": sizes.get(t),
                     "kind": "module" if t.startswith("Module:") else "template"})
    missing = [r for r in rows if not r["target"]]
    # Leaves first: modules, then smaller templates; the root last.
    order = sorted((r for r in missing if r["source"] != root),
                   key=lambda r: (r["kind"] != "module", r["bytes"] or 0))
    order += [r for r in missing if r["source"] == root]
    try:
        td = templatedata(root, source)
    except Exception:
        td = {}
    return {
        "template": root, "exists_on_target": bool(info.get(root) and info[root].target_title),
        "target_name": info[root].target_title if info.get(root) else None,
        "dependencies": rows[1:], "missing_count": len(missing),
        "creation_order": [r["source"] for r in order],
        "templatedata": td,
    }


def source_of(title: str, source: str = "en") -> dict:
    f = fetch_wikitext(_ns_name(title), source)
    return {"title": f["title"], "revid": f["revid"], "wikitext": f["wikitext"]}
