"""
wikikit/translate.py - Translate an article between any two wikis, markup intact.

The model translates prose; code does everything that must be exact. This
split, and the placeholder protocol below, come from wikipedia-translator,
which used it to publish English->Uzbek translations daily.

    start()   fetch -> (trim) -> prepare
              Links, categories and templates are replaced by Wikidata
              placeholders; references and citations are compressed to
              opaque tokens, so the translator never sees (and can never
              alter or invent) a citation.

                [[Ibn Sina|Avicenna]]      -> [[Q8011|Avicenna]]   target wiki has the article
                [[Some Scholar|the scholar]] -> [[LNK3|the scholar]] it does not; needs a name
                [[Category:Persian poets]] -> ⟦CAT:Q7…|Persian poets|⟧
                {{Infobox person|…}}       -> {{TPL:Q6249834|…}}
                <ref>{{cite book|…}}</ref> -> <ref>REF_1a2b3c4d</ref>

    (the translator writes translated.wiki and names.json)

    finish()  placeholders -> target-wiki titles, references restored,
              profile fixes + localization, redundant labels collapsed,
              then every check in wikikit.checks.

Everything lives in a job directory, so the steps can run in separate
processes, sessions, or on another day. Nothing here touches a wiki except
to read.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mwparserfromhell as mwp

from wikikit import checks, labels, profiles
from wikikit.api import site_host
from wikikit.lookup import Lookup
from wikikit.pages import fetch_wikitext, parse_page_ref
from wikikit.trimmer import DEFAULT_APPARATUS, trim_article
from wikikit.wikitext import (
    BRACED_LINK_PLACEHOLDER, CAT_TOKEN, CITATION_LINK_PARAM, CITATION_TEMPLATE_NAME,
    COMPRESSED_PLACEHOLDER, LEFTOVER_LINK_PLACEHOLDER, LINK_PLACEHOLDER, REF_TAG,
    TRANSLATED_LINK_PLACEHOLDER, collapse_newlines, remove_empty_params, strip_comments,
)

REF_COMPRESS_THRESHOLD = 30   # the 23-char "<ref>REF_xxxxxxxx</ref>" must be shorter


# Used when the source wiki's siteinfo cannot be read.
_FALLBACK_INTERWIKI = {"wikt", "wiktionary", "d", "wikidata", "c", "commons", "s", "wikisource",
                       "q", "wikiquote", "b", "wikibooks", "n", "wikinews", "v", "wikiversity",
                       "voy", "wikivoyage", "m", "meta", "mw", "mediawikiwiki", "species", "f", "wikifunctions"}
_FALLBACK_MAGIC = {"!", "=", "!!", "CURRENTYEAR", "CURRENTMONTH", "CURRENTDAY", "CURRENTTIME",
                   "PAGENAME", "PAGENAMEE", "FULLPAGENAME", "NAMESPACE", "SITENAME", "SERVER",
                   "BASEPAGENAME", "SUBPAGENAME", "TALKPAGENAME", "REVISIONYEAR", "NUMBEROFARTICLES",
                   "LOCALYEAR", "CURRENTMONTHNAME", "DEFAULTSORT", "DISPLAYTITLE", "NOTOC", "TOC"}


class LinkContext:
    """
    What a "prefix:" means on the source wiki: a namespace (localized names and
    aliases, e.g. Datei:, Kategorie:), an interwiki/interlanguage prefix
    (wikt:, d:, fr:), or nothing (an article title with a colon). Read from
    the wiki's own siteinfo, so a German or Russian source is classified
    as correctly as an English one.
    """

    def __init__(self, ns: Dict[str, int], interwiki: set, magic: set):
        self.ns, self.interwiki, self.magic = ns, interwiki, magic

    @classmethod
    def for_site(cls, site: str) -> "LinkContext":
        from wikikit.api import api
        ns: Dict[str, int] = {}
        for name in ("file", "image", "media", "template", "help", "portal", "special", "module",
                     "wikipedia", "wp", "user", "user talk", "talk", "draft", "mos", "h"):
            ns[name] = 10 if name == "template" else -1
        ns["category"] = 14
        interwiki, magic = set(_FALLBACK_INTERWIKI), set(_FALLBACK_MAGIC)
        try:
            q = api({"action": "query", "meta": "siteinfo",
                     "siprop": "namespaces|namespacealiases|interwikimap|magicwords"}, site=site)["query"]
            for v in q.get("namespaces", {}).values():
                if v["id"] != 0:
                    for n in (v.get("name"), v.get("canonical")):
                        if n:
                            ns[n.lower()] = v["id"]
            for a in q.get("namespacealiases", []):
                ns[a["alias"].lower()] = a["id"]
            interwiki |= {i["prefix"].lower() for i in q.get("interwikimap", [])}
            for mw in q.get("magicwords", []):
                magic |= {a.rstrip(":") for a in mw.get("aliases", [])}
        except Exception:
            pass
        return cls(ns, interwiki, magic)

    def kind(self, target: str) -> str:
        """'article', 'category', 'skip' for a link target."""
        t = target.strip()
        if not t or t.startswith(("#", ":")):
            return "skip"
        if ":" in t:
            prefix = t.split(":", 1)[0].strip().replace("_", " ").lower()
            if prefix in self.ns:
                return "category" if self.ns[prefix] == 14 else "skip"
            if prefix in self.interwiki or re.fullmatch(r"[a-z]{2,3}(?:-[a-z]+)*", prefix):
                return "skip"
        return "article"

    def template_name(self, name: str):
        """The template's page name without a Template: prefix, or None for magic words/parser functions."""
        n = name.strip()
        if not n or n.startswith("#") or n in self.magic or n.upper() in self.magic:
            return None
        if ":" in n:
            prefix, rest = n.split(":", 1)
            if self.ns.get(prefix.strip().lower()) == 10:
                return rest.strip()
            return None     # {{lc:…}}, {{int:…}}, {{subst:…}}, other namespaces
        return n


# ---------------------------------------------------------------- job dirs

def jobs_dir() -> Path:
    d = profiles.home() / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


_WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _slug(title: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", title, flags=re.UNICODE).strip("_")[:80] or "page"
    return s + "_" if s.lower() in _WIN_RESERVED else s   # "Con" is not a valid name on Windows


def job_path(job: str) -> Path:
    """A job id or a path to a job directory."""
    p = Path(job).expanduser()
    if p.is_dir():
        return p
    p = jobs_dir() / job
    if not p.is_dir():
        raise FileNotFoundError(f"No such job: {job} (looked in {jobs_dir()})")
    return p


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_json(path: Path, obj) -> None:
    _write(path, json.dumps(obj, ensure_ascii=False, indent=2))


def _read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def list_jobs(limit: int = 30) -> List[dict]:
    out = []
    for d in sorted(jobs_dir().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        meta = _read_json(d / "meta.json", {})
        if meta:
            out.append({"job": d.name, "title": meta.get("title"), "pair": f"{meta.get('source_lang')}→{meta.get('target_lang')}",
                        "stage": _stage(d), "updated": _dt.datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="minutes")})
    return out


def _stage(d: Path) -> str:
    if (d / "final.wiki").is_file():
        return "finished"
    if (d / "translated.wiki").is_file():
        return "translated"
    if (d / "prepared.wiki").is_file():
        return "prepared"
    return "created"


# ---------------------------------------------------------------- prepare

CONTENT_CHARS = 40   # visible text above which a template is content, not decoration


def _carries_content(tpl) -> bool:
    """Does the template hold article text (not just settings, dates or codes)?"""
    text = 0
    for p in tpl.params:
        v = mwp.parse(str(p.value)).strip_code().strip()
        if re.fullmatch(r"[\d\s.,:/\-–]*|[a-z]{2,3}|yes|no|left|right|center", v, re.I):
            continue
        text += len(v)
    return text > CONTENT_CHARS


class Preparer:
    """Phase 1, ported from wikipedia-translator's WikiTextProcessor.prepare()."""

    def __init__(self, lookup: Lookup, target: profiles.Profile, ctx: Optional["LinkContext"] = None):
        self.lookup = lookup
        self.ctx = ctx or LinkContext({"category": 14, "file": -1, "image": -1, "template": 10},
                                      set(_FALLBACK_INTERWIKI), set(_FALLBACK_MAGIC))
        self.target = target
        self.link_placeholders: Dict[str, str] = {}   # "LNK3" -> source target
        self.source_labels: Dict[str, str] = {}       # source target -> source label
        self.template_names: Dict[str, str] = {}      # "Q123" -> original template name
        self.removed_templates: List[str] = []
        self.kept_unmapped: List[str] = []             # carry content: kept, reported
        self.ref_map: Dict[str, str] = {}

    # --- references -----------------------------------------------------
    def compress_references(self, wikitext: str) -> str:
        def repl(m: re.Match) -> str:
            ref = m.group(0)
            if len(ref) <= REF_COMPRESS_THRESHOLD:
                return ref
            rid = hashlib.md5(ref.encode()).hexdigest()[:8]
            self.ref_map[rid] = ref
            return f"<ref>REF_{rid}</ref>"
        return re.sub(REF_TAG, repl, wikitext, flags=re.DOTALL | re.IGNORECASE)

    def compress_citations(self, wikitext: str) -> str:
        """Bare {{cite …}} outside refs: bibliographic data stays as published."""
        code = mwp.parse(wikitext)
        for tpl in code.filter_templates(recursive=False):
            if not re.match(CITATION_TEMPLATE_NAME, str(tpl.name), re.IGNORECASE):
                continue
            original = str(tpl)
            token = "CITE_" + hashlib.md5(original.encode()).hexdigest()[:8]
            self.ref_map[token] = original
            code.replace(tpl, token)
        return str(code)

    @staticmethod
    def _article_target(t: str) -> bool:
        return bool(t) and ":" not in t

    def citation_link_targets(self) -> set:
        targets = set()
        for original in self.ref_map.values():
            code = mwp.parse(original)
            for wl in code.filter_wikilinks():
                t = str(wl.title).strip()
                if self._article_target(t):
                    targets.add(t)
            for tpl in code.filter_templates():
                for p in tpl.params:
                    v = str(p.value).strip()
                    if re.match(CITATION_LINK_PARAM, str(p.name).strip(), re.I) and self._article_target(v):
                        targets.add(v)
        return targets

    def resolve_citation_links(self) -> Tuple[int, int]:
        """A citation keeps the source's visible text; only link targets move to the target wiki."""
        linked = unlinked = 0
        for key, original in self.ref_map.items():
            code = mwp.parse(original)
            for wl in code.filter_wikilinks():
                t = str(wl.title).strip()
                if not self._article_target(t):
                    continue
                label = str(wl.text).strip() if wl.text else t
                tgt = self._target_title(t)
                if tgt:
                    code.replace(wl, f"[[{tgt}]]" if tgt == label else f"[[{tgt}|{label}]]")
                    linked += 1
                else:
                    code.replace(wl, label)
                    unlinked += 1
            for tpl in code.filter_templates():
                for p in list(tpl.params):
                    v = str(p.value).strip()
                    if not (re.match(CITATION_LINK_PARAM, str(p.name).strip(), re.I) and self._article_target(v)):
                        continue
                    tgt = self._target_title(v)
                    if tgt:
                        p.value = str(p.value).replace(v, tgt, 1)
                        linked += 1
                    else:
                        tpl.remove(p)
                        unlinked += 1
            self.ref_map[key] = str(code)
        return linked, unlinked

    def _target_title(self, title: str) -> Optional[str]:
        info = self.lookup.pages.get(title)
        return info.target_title if info else None

    # --- main -----------------------------------------------------------
    def prepare(self, raw: str) -> Tuple[str, dict]:
        text = remove_empty_params(raw)
        text = self.compress_references(text)
        text = self.compress_citations(text)
        text = strip_comments(text)
        code = mwp.parse(text)

        cats, links, tpls = [], [], []
        for wl in code.filter_wikilinks():
            t = str(wl.title).strip()
            kind = self.ctx.kind(t)
            if kind == "category":
                cats.append((t, wl, str(wl.text).strip() if wl.text else ""))
            elif kind == "article" and not re.fullmatch(r"Q\d+", t):
                links.append((t, wl, str(wl.text).strip() if wl.text else t))
        for tpl in code.filter_templates():
            raw_name = str(tpl.name).strip()
            if raw_name.startswith("TPL:"):
                continue
            name = self.ctx.template_name(raw_name)
            if name:
                tpls.append((name, tpl))

        def lookup_key(t: str) -> str:
            return t.split("#", 1)[0].strip() or t

        titles = {lookup_key(t) for t, _, _ in cats + links}
        titles |= {f"Template:{n}" for n, _ in tpls}
        titles |= self.citation_link_targets()
        self.lookup.page_info(titles)

        link_qids, cat_qids, tpl_qids = set(), set(), set()

        for t, wl, sort_key in cats:
            info = self.lookup.pages.get(t)
            if info and info.qid:
                cat_qids.add(info.qid)
            # Q0 = no item: the translator still translates the name, and
            # finish() puts it in the target wiki's category namespace.
            code.replace(wl, f"⟦CAT:{info.qid if info and info.qid else 'Q0'}|{t.split(':', 1)[1].strip()}|{sort_key}⟧")

        placeholder_for: Dict[str, str] = {}
        unresolved: List[str] = []
        for t, wl, label in links:
            if t.startswith(":"):
                continue   # [[:fa:…]], [[:Category:…]] — not an article to map
            info = self.lookup.pages.get(lookup_key(t))
            if info and info.qid and info.target_title:
                link_qids.add(info.qid)
                wl.title = info.qid
                wl.text = label
            else:
                unresolved.append(t)
                token = placeholder_for.setdefault(t, f"LNK{len(placeholder_for) + 1}")
                if label != t:
                    self.source_labels.setdefault(t, label)
                wl.title = token
                wl.text = label
        self.link_placeholders = {tok: t for t, tok in placeholder_for.items()}

        cites = self.resolve_citation_links() if self.ref_map else (0, 0)

        fallbacks = self.target.template_fallbacks
        to_remove = []
        for name, tpl in tpls:
            info = self.lookup.pages.get(f"Template:{name}")
            if info and info.qid and info.target_title:
                tpl_qids.add(info.qid)
                self.template_names.setdefault(info.qid, name)
                tpl.name = f"TPL:{info.qid}" + ("\n" if str(tpl.name).endswith("\n") else "")
            elif name.lower() in fallbacks:
                tpl.name = fallbacks[name.lower()] + ("\n" if str(tpl.name).endswith("\n") else "")
            elif self.target.drop_unmapped_templates and not _carries_content(tpl):
                to_remove.append(tpl)
            else:
                # A template holding prose (a poem, a quotation, a translation
                # table) is kept under its source name even when the target
                # wiki lacks it: dropping it silently deleted five poem
                # stanzas from a test article. A red template name in preview
                # is visible; lost text is not.
                self.kept_unmapped.append(name)
        for tpl in to_remove:
            try:
                self.removed_templates.append(str(tpl.name).strip())
                code.remove(tpl)
            except ValueError:
                pass   # already gone with its parent

        counts = {
            "links_mapped": len(link_qids), "links_unmapped": len(self.link_placeholders),
            "categories_mapped": len(cat_qids), "templates_mapped": len(tpl_qids),
            "templates_removed": sorted(set(self.removed_templates)),
            "templates_kept_without_target": sorted(set(self.kept_unmapped)),
            "references_compressed": len(self.ref_map),
            "citation_links": {"linked": cites[0], "unlinked": cites[1]},
            "failed_lookups": sorted(self.lookup.failed),
        }
        return str(code), counts


def start(page: str, target_lang: str, source: str = "en", mode: str = "auto",
          wikitext: Optional[str] = None) -> dict:
    """
    Create a translation job: fetch, trim if needed, prepare.

    `page` is a title, "lang:Title" or a URL. Pass `wikitext` to translate
    text you already have (page is then only the job's name).
    """
    host, title = parse_page_ref(page, source)
    source_lang = host.split(".")[0]
    family = host.split(".")[1] if host.count(".") >= 2 else "wikipedia"
    if wikitext is None:
        fetched = fetch_wikitext(title, host)
    else:
        fetched = {"title": title, "redirected_from": None, "revid": None, "timestamp": None,
                   "qid": None, "wikitext": wikitext, "site": site_host(host)}
    src_prof = profiles.load(source_lang)
    tgt_prof = profiles.load(target_lang)

    d = jobs_dir() / f"{_slug(fetched['title'])}.{source_lang}-{target_lang}"
    d.mkdir(parents=True, exist_ok=True)
    for stale in ("translated.wiki", "names.json", "final.wiki", "report.json"):
        (d / stale).unlink(missing_ok=True)
    raw = fetched["wikitext"]
    _write(d / "source.wiki", raw)

    trim_info = {"trimmed": False, "reason": "full requested" if mode == "full" else "under threshold"}
    text = raw
    if mode == "trim" or (mode == "auto" and len(raw.encode("utf-8")) > tgt_prof.trim_threshold):
        text, trim_info = trim_article(
            raw, src_prof.source_setting("apparatus_heading", DEFAULT_APPARATUS), tgt_prof.trim_min_lead)
    _write(d / "input.wiki", text)

    lookup = Lookup(source=host, target_lang=target_lang, family=family)
    prep = Preparer(lookup, tgt_prof, LinkContext.for_site(host))
    prepared, counts = prep.prepare(text)
    _write(d / "prepared.wiki", prepared)

    links = [{"id": tok, "source_target": t, "source_label": prep.source_labels.get(t, "")}
             for tok, t in prep.link_placeholders.items()]
    meta = {
        "job": d.name, "title": fetched["title"], "redirected_from": fetched["redirected_from"],
        "source_site": fetched["site"], "source_lang": source_lang, "target_lang": target_lang,
        "family": family, "revid": fetched["revid"], "source_timestamp": fetched["timestamp"],
        "source_qid": fetched["qid"], "mode": mode, "trim": trim_info,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    _write_json(d / "meta.json", meta)
    _write_json(d / "state.json", {
        "ref_map": prep.ref_map, "link_placeholders": prep.link_placeholders,
        "source_labels": prep.source_labels, "template_names": prep.template_names,
        "removed_templates": prep.removed_templates, "counts": counts,
        "lookup": lookup.to_state(),
    })
    _write_json(d / "links.json", links)

    source_warnings = tgt_prof.check_source(raw) if tgt_prof.module else []
    return {
        "job": d.name, "dir": str(d), "title": fetched["title"], "revid": fetched["revid"],
        "source_qid": fetched["qid"],
        "bytes": {"source": len(raw.encode()), "prepared": len(prepared.encode())},
        "trim": {k: trim_info.get(k) for k in ("trimmed", "reason", "cut_sections", "thin_lead") if k in trim_info},
        "counts": counts,
        "prepared_path": str(d / "prepared.wiki"),
        "links_path": str(d / "links.json"),
        "write_translation_to": str(d / "translated.wiki"),
        "write_names_to": str(d / "names.json"),
        "style_guide": str(tgt_prof.style_path) if tgt_prof.style_path else None,
        "unmapped_links": len(links),
        "source_warnings": source_warnings,
    }


# ---------------------------------------------------------------- finalize

def _repair_placeholders(text: str) -> str:
    """{{LNK8|label}} — the model's occasional brace form — back to [[LNK8|label]]."""
    return re.sub(BRACED_LINK_PLACEHOLDER, r"[[\1|\2]]", text)


def _restore_references(text: str, ref_map: Dict[str, str]) -> Tuple[str, int, List[str]]:
    restored = 0
    for rid, original in ref_map.items():
        if rid.startswith("CITE_"):
            if rid in text:
                text = text.replace(rid, original)
                restored += 1
            continue
        ph = f"<ref>REF_{rid}</ref>"
        if ph in text:
            text = text.replace(ph, original)
            restored += 1
            continue
        loose = re.compile(r"(?:<ref[^>]*>\s*)?REF_" + re.escape(rid) + r"(?:\s*</ref>)?")
        text, hits = loose.subn(lambda _m: original, text)
        restored += bool(hits)
    leftover = sorted(set(re.findall(COMPRESSED_PLACEHOLDER, text)))
    return text, restored, leftover


def finish(job: str) -> dict:
    """Turn translated.wiki (+ names.json) into final.wiki and report.json."""
    d = job_path(job)
    meta = _read_json(d / "meta.json")
    state = _read_json(d / "state.json")
    tpath = d / "translated.wiki"
    if not tpath.is_file():
        raise FileNotFoundError(f"{tpath} does not exist yet — translate prepared.wiki first.")
    translated = tpath.read_text(encoding="utf-8")
    names = _read_json(d / "names.json", {}) or {}
    link_names: Dict[str, str] = names.get("links") or {
        k: v for k, v in names.items() if re.fullmatch(LINK_PLACEHOLDER, k)}
    tgt = profiles.load(meta["target_lang"])
    lookup = Lookup.from_state(state["lookup"], meta["source_site"], meta["target_lang"], meta.get("family", "wikipedia"))
    placeholders: Dict[str, str] = state["link_placeholders"]

    code = mwp.parse(_repair_placeholders(translated))
    chosen: Dict[str, str] = {}
    from_label, still_source, unknown = [], [], []

    def page_name(token: str, label: str) -> Optional[str]:
        src_target = placeholders.get(token)
        if src_target is None:
            unknown.append(token)
            return tgt.clean_title(label)
        if src_target in chosen:
            return chosen[src_target]
        name = tgt.clean_title(link_names.get(token))
        if not name:
            name = tgt.clean_title(label) if label and label != src_target else None
            if name:
                from_label.append({"source": src_target, "name": name})
            else:
                name = src_target
                still_source.append(src_target)
        chosen[src_target] = name
        return name

    qid_title = {i.qid: i.target_title for i in lookup.pages.values() if i.qid and i.target_title}
    for wl in code.filter_wikilinks():
        t = str(wl.title).strip()
        label = str(wl.text).strip() if wl.text else ""
        if re.fullmatch(r"Q\d+", t):
            title = qid_title.get(t) or lookup.sitelink(t)
            if title:
                wl.title = title
                if not label or label == title:
                    wl.text = None
        elif re.fullmatch(LINK_PLACEHOLDER, t):
            name = page_name(t, label)
            if name:
                wl.title = name
                if not label or label == name:
                    wl.text = None
    text = str(code)

    leftover_links = sorted(set(re.findall(LEFTOVER_LINK_PLACEHOLDER, text)))

    cat_ns = tgt.category_ns
    if "category" not in tgt.data.get("namespaces", {}):
        # No profile says it: ask the target wiki (canonical "Category" also works).
        try:
            from wikikit.lookup import siteinfo
            cat_ns = siteinfo(f"{meta['target_lang']}.{meta.get('family', 'wikipedia')}")["namespaces"].get("14") or cat_ns
        except Exception:
            pass

    def cat_repl(m: re.Match) -> str:
        qid, name, sort_key = m.group(1), m.group(2).strip(), m.group(3).strip()
        suffix = f"|{sort_key}" if sort_key else ""
        title = qid_title.get(qid) or (lookup.sitelink(qid) if qid != "Q0" else None)
        if title:
            title = title if ":" in title else f"{cat_ns}:{title}"
            return f"[[{title}{suffix}]]"
        return f"[[{cat_ns}:{name}{suffix}]]"

    text = re.sub(CAT_TOKEN, cat_repl, text)
    # Categories that had no Wikidata item at all keep the source namespace.
    text = re.sub(r"\[\[\s*[Cc]ategory\s*:", f"[[{cat_ns}:", text)

    code2 = mwp.parse(text)
    dropped_tpl = []
    for tpl in code2.filter_templates():
        name = str(tpl.name).strip()
        if name.startswith("TPL:Q"):
            qid = name[4:]
            title = qid_title.get(qid) or lookup.sitelink(qid)
            nl = "\n" if str(tpl.name).endswith("\n") else ""
            if title:
                tpl.name = (title.split(":", 1)[1] if ":" in title else title).strip() + nl
            else:
                original = state["template_names"].get(qid, qid)
                fb = tgt.template_fallbacks.get(original.lower())
                if fb:
                    tpl.name = fb + nl
                elif tgt.drop_unmapped_templates:
                    dropped_tpl.append(tpl)
                else:
                    tpl.name = original + nl
    for tpl in dropped_tpl:
        try:
            code2.remove(tpl)
        except ValueError:
            pass
    text = str(code2)

    text, restored, leftover_refs = _restore_references(text, state["ref_map"])
    text = tgt.post_process(text)
    text, localized = tgt.localize(text)
    text, mismatches = labels.collapse(text, tgt.same_name)
    text = collapse_newlines(text).strip() + "\n"
    _write(d / "final.wiki", text)

    source_input = (d / "input.wiki").read_text(encoding="utf-8")
    report = {
        "job": d.name, "title": meta["title"], "pair": f"{meta['source_lang']}→{meta['target_lang']}",
        "final_path": str(d / "final.wiki"),
        "links": {"from_names_json": len(chosen) - len(from_label) - len(still_source),
                  "name_taken_from_label": from_label, "left_in_source_language": still_source,
                  "unknown_placeholders": sorted(set(unknown))},
        "leftover_placeholders": leftover_links + leftover_refs,
        "references": {"restored": restored, "total": len(state["ref_map"])},
        "localization_replacements": localized,
        "label_mismatches": [{"target": t, "label": l} for t, l in mismatches],
        "failed_lookups": state["counts"].get("failed_lookups", []),
        "templates": {
            "removed": state["counts"].get("templates_removed", []),
            "kept_without_target": state["counts"].get("templates_kept_without_target", []),
        },
        "checks": checks.run(source_input, text, meta, tgt),
        "title_suggestion": names.get("title"),
    }
    _write_json(d / "report.json", report)
    return report


def job_status(job: str) -> dict:
    d = job_path(job)
    meta = _read_json(d / "meta.json", {})
    out = {"job": d.name, "dir": str(d), "stage": _stage(d), "meta": meta,
           "files": sorted(p.name for p in d.iterdir())}
    rep = _read_json(d / "report.json")
    if rep:
        out["report_summary"] = checks.summarize(rep)
    return out


# ---------------------------------------------------------------- publish prep

def publish_prep(job: str, target_title: Optional[str] = None) -> dict:
    """
    Everything a human needs to publish by hand — and nothing that publishes.

    CC BY-SA requires a translation to credit its source; the edit summary
    below does that with a permanent link to the exact revision translated,
    and discloses machine assistance as en.wiki's LLM guideline (2026)
    requires and most wikis expect.
    """
    import urllib.parse
    d = job_path(job)
    meta = _read_json(d / "meta.json")
    report = _read_json(d / "report.json")
    if not report:
        raise FileNotFoundError("Run finish first: there is no report.json")
    names = _read_json(d / "names.json", {}) or {}
    title = target_title or names.get("title") or meta["title"]
    tgt = profiles.load(meta["target_lang"])
    template = tgt.attribution().get("edit_summary") or (
        "Translated from [[:{source_lang}:{title}]] ([[:{source_lang}:Special:PermanentLink/{revid}|revision {revid}]]); machine-assisted, reviewed by a human")
    summary = template.format(source_lang=meta["source_lang"], title=meta["title"], revid=meta.get("revid") or "?")
    target_host = f"{meta['target_lang']}.{meta.get('family', 'wikipedia')}.org"
    edit_url = f"https://{target_host}/w/index.php?" + urllib.parse.urlencode({"title": title, "action": "edit"})
    permalink = (f"https://{meta['source_site']}/w/index.php?oldid={meta['revid']}" if meta.get("revid") else None)
    blocking = report.get("checks", {}).get("blocking", [])
    disclosure = tgt.attribution().get("disclosure_template")
    return {
        "target_title": title,
        "edit_url": edit_url,
        "edit_summary": summary,
        "source_permalink": permalink,
        "final_path": str(d / "final.wiki"),
        "ready": not blocking and not report.get("leftover_placeholders") and not report.get("failed_lookups"),
        "failed_lookups": report.get("failed_lookups", []),
        "disclosure_template": disclosure,
        "blocking": blocking,
        "checklist": [
            "Read the whole text in the target language — you are the reviewer the policy requires.",
            "Verify every number listed under checks.numbers against the source.",
            "Open the preview (Show preview) and look for red template names and Cite errors.",
            "Paste the edit summary exactly; it carries the CC BY-SA attribution.",
            "Add the Wikidata sitelink after saving (the item is " + str(meta.get("source_qid")) + ").",
        ],
        "note": "wiki-agent-kit never saves pages. Open edit_url, paste final.wiki, review, and save yourself.",
    }
