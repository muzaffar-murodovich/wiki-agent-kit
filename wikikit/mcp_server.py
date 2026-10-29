"""
wikikit/mcp_server.py - The kit's tools, exposed to Claude Code over MCP (stdio).

Every tool is read-only against the wikis (the HTTP client refuses write
actions outright) and returns JSON. Article text never travels through a
tool result: tools read and write files in a job directory and return paths,
so a 40 KB article does not flood the conversation and parallel translator
agents do not share a context.

Run:  uv run --project <plugin dir> python -m wikikit.mcp_server
"""

from __future__ import annotations

import functools
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from wikikit import cite, commons, finder, jev, lookup, pages, profiles, templates, translate, wikidata
from wikikit.api import WriteRefused, user_agent

server = MCPServer(
    "wikikit",
    instructions=(
        "Read-only tools for Wikimedia editors. Nothing here can edit a wiki: you draft, the human "
        "publishes. Translate with translate_start -> (translator writes translated.wiki + names.json) "
        "-> translate_finish -> publish_prep. Pass article text through files, never through tool "
        "arguments."
    ),
)

_RO = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
_LOCAL = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


def tool(local: bool = False):
    """Register a tool whose failures come back as {"ok": false, "error": ...}, never a crash."""
    def deco(fn: Callable):
        @functools.wraps(fn)
        def wrapped(*a, **kw):
            try:
                res = fn(*a, **kw)
                return {"ok": True, **res} if isinstance(res, dict) else {"ok": True, "result": res}
            except WriteRefused as e:
                return {"ok": False, "error": str(e), "refused": True}
            except Exception as e:  # noqa: BLE001 — every failure must reach the agent as data
                return {"ok": False, "error": f"{type(e).__name__}: {e}",
                        "where": traceback.format_exc(limit=2).splitlines()[-1]}
        return server.tool(annotations=_LOCAL if local else _RO)(wrapped)
    return deco


# ------------------------------------------------------------- translation

@tool(local=True)
def translate_start(page: str, target_lang: str, source_lang: str = "en", mode: str = "auto",
                    wikitext_file: Optional[str] = None) -> dict:
    """Create a translation job: fetch the source article, trim it if long, and replace links,
    categories, templates and references with Wikidata placeholders.

    page: title, "lang:Title" or URL. mode: auto (trim above the target profile's threshold),
    full, or trim. wikitext_file: translate this local file instead of fetching.
    Returns the job id and the paths the translator reads (prepared_path, links_path,
    style_guide) and writes (write_translation_to, write_names_to)."""
    text = Path(wikitext_file).read_text(encoding="utf-8") if wikitext_file else None
    return translate.start(page, target_lang, source_lang, mode, text)


@tool(local=True)
def translate_finish(job: str) -> dict:
    """Resolve placeholders in the job's translated.wiki (using names.json for unmapped links),
    restore references, apply the target profile's fixes and localization, collapse redundant
    link labels, and run every check. Writes final.wiki and report.json; returns the report."""
    return translate.finish(job)


@tool(local=True)
def job_status(job: str) -> dict:
    """Stage, files and report summary of one translation job."""
    return translate.job_status(job)


@tool(local=True)
def jobs_list(limit: int = 30) -> dict:
    """Most recent translation jobs with their stage (prepared / translated / finished)."""
    return {"jobs": translate.list_jobs(limit), "jobs_dir": str(translate.jobs_dir())}


@tool(local=True)
def publish_prep(job: str, target_title: Optional[str] = None) -> dict:
    """The edit URL, an attribution edit summary (CC BY-SA + AI disclosure), and a review
    checklist for a finished job. Does NOT publish: the human opens the URL and saves."""
    return translate.publish_prep(job, target_title)


# ------------------------------------------------------------- pages & lookups

@tool()
def page_info(titles: List[str], target_lang: str, source_lang: str = "en") -> dict:
    """For each source-wiki title: redirect target, Wikidata QID, and the title of the same
    article on the target-language wiki (null when it does not exist there)."""
    lk = lookup.Lookup(source=source_lang, target_lang=target_lang)
    info = lk.page_info(titles, with_length=True)
    return {"pages": {t: i.as_dict() for t, i in info.items()}, "failed": sorted(lk.failed)}


@tool()
def fetch_page(title: str, site: str = "en", save_to: Optional[str] = None) -> dict:
    """Current wikitext of a page on any wiki (site: "en", "uz.wiktionary", "commons", ...).
    Text up to 6000 characters is returned inline; longer text is saved to a file
    (save_to, or $WIKIKIT_HOME/pages/) and only the path is returned."""
    f = pages.fetch_wikitext(title, site)
    text = f.pop("wikitext")
    if len(text) <= 6000 and not save_to:
        return {**f, "wikitext": text}
    path = Path(save_to) if save_to else profiles.home() / "pages" / f"{translate._slug(f['title'])}.{site}.wiki"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {**f, "bytes": len(text.encode()), "saved_to": str(path)}


@tool()
def search_pages(query: str, site: str = "en", limit: int = 10) -> dict:
    """Full-text search on a wiki."""
    return {"results": pages.search(query, site, limit)}


@tool()
def interlanguage_links(title: str, site: str = "en") -> dict:
    """Every other-language version of a page, {lang: title}."""
    return {"langlinks": pages.langlinks(title, site)}


@tool()
def site_info(site: str) -> dict:
    """Namespaces (with local names and aliases) and language of a wiki."""
    return lookup.siteinfo(site)


@tool(local=True)
def profile_info(lang: Optional[str] = None) -> dict:
    """The language profile used for a target wiki (style guide path, hooks, localization rule
    count), or the list of available profiles when lang is omitted."""
    if not lang:
        return {"available": profiles.available(), "user_profiles_dir": str(profiles.home() / "profiles")}
    return profiles.load(lang).summary()


# ------------------------------------------------------------- finding work

@tool()
def missing_in_category(category: str, target_lang: str, source_lang: str = "en", limit: int = 40) -> dict:
    """Articles of a source-wiki category that the target wiki lacks and the queue has not seen,
    smallest first, with size and suggested mode (full / trim)."""
    q = finder.Queue(source_lang, target_lang)
    return finder.list_missing(category, target_lang, source_lang, limit, q,
                               profiles.load(target_lang).trim_threshold)


@tool()
def missing_linked(page: str, target_lang: str, source_lang: str = "en", limit: int = 60) -> dict:
    """Articles a page links to that the target wiki lacks — the red links a translation of
    that page would have — smallest first."""
    rows = finder.linked_articles(page, target_lang, source_lang)
    miss = sorted(((t, r["size"]) for t, r in rows.items() if not r["target"]), key=lambda x: x[1])
    return {"page": page, "linked": len(rows), "missing": len(miss),
            "articles": [{"title": t, "size": s} for t, s in miss[:limit]]}


@tool()
def category_tree(category: str, source_lang: str = "en", target_lang: Optional[str] = None) -> dict:
    """Parent and child categories, each labelled with its status in the queue (if target_lang
    is given): new / open / exhausted / skipped."""
    q = finder.Queue(source_lang, target_lang) if target_lang else None
    lab = lambda c: (q.category_status(c) if q else None) or "new"
    return {"parents": [{"category": c, "status": lab(c)} for c in finder.parent_categories(category, source_lang)],
            "children": [{"category": c, "status": lab(c)} for c in finder.subcategories(category, source_lang)]}


@tool()
def screen_evidence(titles: List[str], source_lang: str = "en") -> dict:
    """Each article's own topical categories (date and maintenance buckets removed). This is
    evidence for YOUR judgment on whether a topic fits the user's policy, not a verdict."""
    return {"categories": finder.evidence(titles, source_lang)}


@tool()
def pageviews(titles: List[str], source_lang: str = "en", days: int = 30) -> dict:
    """Human pageviews per article over the last N days (max 60 titles) — to rank candidates."""
    return {"views": finder.pageviews(titles, source_lang, days)}


# ------------------------------------------------------------- queue

def _queue(source_lang: str, target_lang: str) -> finder.Queue:
    return finder.Queue(source_lang, target_lang)


@tool(local=True)
def queue_add(titles: List[str], target_lang: str, source_lang: str = "en",
              category: str = "", note: str = "") -> dict:
    """Add articles to the worklist after confirming each exists and is still missing on the
    target wiki. Returns per title: added / dup:<status> / has_target:<title> / missing."""
    lk = lookup.Lookup(source=source_lang, target_lang=target_lang)
    info = lk.page_info(titles, with_length=True)
    q = _queue(source_lang, target_lang)
    out = {}
    for t in titles:
        i = info.get(t)
        if t in lk.failed:
            out[t] = "lookup_failed"      # an API error, not an absent page: try again
        elif not i or not i.exists:
            out[t] = "missing"
        elif i.target_title:
            out[t] = f"has_target:{i.target_title}"
        else:
            out[t] = q.add(i.resolved, i.length or 0, category, note)
    q.save()
    return {"results": out}


@tool(local=True)
def queue_reject(titles: List[str], reason: str, target_lang: str, source_lang: str = "en",
                 category: str = "") -> dict:
    """Reject articles with a REQUIRED reason (in English), so 'why was X left out?' has an
    answer later. A queued article can be pulled back out; a translated one cannot."""
    q = _queue(source_lang, target_lang)
    out = {t: q.reject(t, reason, category) for t in titles}
    q.save()
    return {"results": out}


@tool(local=True)
def queue_requeue(titles: List[str], target_lang: str, source_lang: str = "en") -> dict:
    """Undo a rejection."""
    q = _queue(source_lang, target_lang)
    out = {t: q.requeue(t) for t in titles}
    q.save()
    return {"results": out}


@tool(local=True)
def queue_mark(titles: List[str], status: str, target_lang: str, source_lang: str = "en") -> dict:
    """Move articles forward: translated or published. A status never goes backwards."""
    q = _queue(source_lang, target_lang)
    out = {t: q.set_status(t, status) for t in titles}
    q.save()
    return {"results": out}


@tool(local=True)
def queue_next(target_lang: str, source_lang: str = "en", n: int = 8) -> dict:
    """The next N queued articles, smallest first."""
    return {"next": _queue(source_lang, target_lang).next(n)}


@tool(local=True)
def queue_status(target_lang: str, source_lang: str = "en") -> dict:
    """Counts of queued / translated / published / rejected articles and categories."""
    return _queue(source_lang, target_lang).status()


@tool(local=True)
def queue_rejected(target_lang: str, source_lang: str = "en", reason_contains: str = "",
                   category: str = "", limit: int = 30) -> dict:
    """Rejected articles with their recorded reason, newest first."""
    return {"rejected": _queue(source_lang, target_lang).rejected(reason_contains, category)[:limit]}


@tool(local=True)
def category_skip(category: str, reason: str, target_lang: str, source_lang: str = "en") -> dict:
    """Set a category aside for good (e.g. named after a movement the user's policy excludes)."""
    q = _queue(source_lang, target_lang)
    q.mark_category(category, "skipped", reason=reason)
    q.save()
    return {"category": category, "status": "skipped"}


# ------------------------------------------------------------- wikidata

@tool()
def wd_entity(qid: str, langs: str = "en") -> dict:
    """A Wikidata item: labels, descriptions, aliases (langs: "uz|en"), key statements with
    value labels, and sitelinks."""
    return wikidata.entity(qid, langs)


@tool()
def wd_missing_terms(qids: List[str], lang: str) -> dict:
    """Which items lack a label or description in `lang`, with the English ones for context."""
    return {"items": wikidata.missing_terms(qids, lang)}


@tool()
def wd_search(text: str, lang: str = "en", limit: int = 7) -> dict:
    """Search Wikidata items — always do this before proposing a new item."""
    return {"results": wikidata.search(text, lang, limit)}


@tool()
def wd_check_quickstatements(quickstatements: str) -> dict:
    """Lint a QuickStatements V1 batch you drafted: unknown items/properties, wrong value types,
    duplicates of existing statements, statements without a source. The human runs it."""
    return wikidata.check_quickstatements(quickstatements)


@tool()
def wd_infobox_check(title: str, site: str = "en") -> dict:
    """Birth/death years where an article's infobox disagrees with its Wikidata item."""
    f = pages.fetch_wikitext(title, site)
    if not f["qid"]:
        return {"title": f["title"], "qid": None, "conflicts": [], "note": "page has no Wikidata item"}
    return {"title": f["title"], "qid": f["qid"], "conflicts": wikidata.infobox_vs_wikidata(f["wikitext"], f["qid"])}


# ------------------------------------------------------------- templates & media

@tool()
def template_port_plan(template: str, target_lang: str, source_lang: str = "en") -> dict:
    """Everything needed to bring a template or module to the target wiki: its transcluded
    templates/modules, which already exist there (and under what name), TemplateData
    parameters, and a leaves-first creation order for the missing ones."""
    return templates.port_plan(template, target_lang, source_lang)


@tool()
def commons_file_info(files: List[str]) -> dict:
    """Licence, author, description and thumbnail of Commons files."""
    return {"files": commons.file_info(files)}


@tool()
def commons_search(query: str, limit: int = 10) -> dict:
    """Search Commons for images, with licence and author."""
    return {"results": commons.search(query, limit)}


@tool()
def article_images(title: str, site: str = "en") -> dict:
    """Content images used in an article (interface icons filtered out)."""
    return {"images": commons.images_in_article(title, site)}


# ------------------------------------------------------------- citations

@tool(local=True)
def cite_claims(path: str, limit: int = 40) -> dict:
    """Sentences that carry a reference, with each reference's URL/title/quote, from a local
    wikitext file (e.g. a job's final.wiki or input.wiki)."""
    items = cite.claims(Path(path).read_text(encoding="utf-8"))
    return {"total": len(items), "claims": items[:limit]}


@tool()
def cite_passages(url: str, claim: str, k: int = 3) -> dict:
    """Fetch a cited web page and return the k passages most relevant to the claim, for you
    (or Jev) to judge: supports / contradicts / says nothing."""
    text = cite.fetch_text(url)
    return {"url": url, "chars": len(text), "passages": cite.passages(text, claim, k)}


@tool()
def jev_cite_check(claim: str, passages: List[str]) -> dict:
    """Ask TypeSafe Jev whether the passages support the claim. Returns a verdict with a
    calibrated confidence; auto=true means confident enough to skip human review.
    Needs TYPESAFE_API_KEY; otherwise judge the passages yourself."""
    return jev.cite_check(claim, passages)


@tool()
def jev_classify(items: Dict[str, str], question: str, options: Dict[str, str]) -> dict:
    """Route many items (id -> text) to one of a few options with TypeSafe Jev, each with a
    confidence. Use for bulk screening; send low-confidence items to the user.
    Needs TYPESAFE_API_KEY."""
    return {"results": jev.classify(items, question, options)}


@tool(local=True)
def kit_status() -> dict:
    """Configuration check: work directory, contact for the User-Agent, Jev availability."""
    from wikikit.api import setting
    return {
        "home": str(profiles.home()), "user_agent": user_agent(),
        "contact_set": bool(setting("WIKIKIT_CONTACT")),
        "jev_available": jev.available(), "profiles": profiles.available(),
        "writes_possible": False,
    }


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
