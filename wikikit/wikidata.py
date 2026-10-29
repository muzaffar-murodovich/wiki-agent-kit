"""
wikikit/wikidata.py - Reading Wikidata, and drafting (never running) edits.

Wikidata is what makes the kit language-independent: every link, category
and template is mapped through its item. These helpers also serve the
Wikidata-side workflows:

  * entity()            a compact, human-readable view of an item
  * missing_terms()     which items lack a label/description in a language
  * search()            find existing items before proposing a new one
  * properties()        label + datatype of properties, to validate drafts
  * check_quickstatements()  lint a QuickStatements batch the agent drafted;
                        the human pastes it into QuickStatements themselves
  * infobox_vs_wikidata()    where an article's infobox and its item disagree
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

import mwparserfromhell as mwp

from wikikit.api import BATCH_SIZE, api

KEY_PROPS = ["P31", "P279", "P21", "P27", "P106", "P569", "P570", "P19", "P20",
             "P17", "P131", "P625", "P571", "P576", "P18", "P1412", "P140", "P737", "P1066", "P802"]


def _get_entities(ids: List[str], props: str, langs: str = "") -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for i in range(0, len(ids), BATCH_SIZE):
        params = {"action": "wbgetentities", "ids": "|".join(ids[i:i + BATCH_SIZE]), "props": props}
        if langs:
            params["languages"] = langs
            params["languagefallback"] = "1"
        out.update(api(params, site="wikidata").get("entities", {}))
    return out


def _labels(ids: Iterable[str], lang: str) -> Dict[str, str]:
    ids = [i for i in dict.fromkeys(ids) if re.fullmatch(r"[QPL]\d+", i)]
    if not ids:
        return {}
    ents = _get_entities(ids, "labels", f"{lang}|en")
    out = {}
    for i, e in ents.items():
        lab = e.get("labels", {})
        out[i] = (lab.get(lang) or lab.get("en") or {}).get("value", i)
    return out


def _value(snak: dict) -> Optional[str]:
    dv = snak.get("datavalue")
    if not dv:
        return snak.get("snaktype")
    v, t = dv["value"], dv["type"]
    if t == "wikibase-entityid":
        return v.get("id")
    if t == "time":
        prec = v.get("precision", 11)
        tm = v["time"].lstrip("+")
        cal = " (Julian)" if v.get("calendarmodel", "").endswith("Q1985786") else ""
        return (tm[:4] if prec <= 9 else tm[:7] if prec == 10 else tm[:10]) + cal
    if t == "quantity":
        return v.get("amount", "").lstrip("+") + ("" if v.get("unit") in ("1", None) else " " + v["unit"].rsplit("/", 1)[-1])
    if t == "globecoordinate":
        return f"{v['latitude']},{v['longitude']}"
    if t == "monolingualtext":
        return f"{v['text']} ({v['language']})"
    return str(v)


def entity(qid: str, langs: str = "en", props: Optional[List[str]] = None) -> dict:
    """Labels, descriptions, aliases, sitelinks and key statements, with value labels resolved."""
    lang_list = [l for l in langs.split("|") if l] or ["en"]
    e = _get_entities([qid], "labels|descriptions|aliases|claims|sitelinks", "|".join(set(lang_list + ["en"]))).get(qid)
    if not e or "missing" in e:
        raise LookupError(f"No such Wikidata item: {qid}")
    claims = e.get("claims", {})
    wanted = props or [p for p in KEY_PROPS if p in claims]
    statements: Dict[str, List[str]] = {}
    for p in wanted:
        statements[p] = [x for x in (_value(c["mainsnak"]) for c in claims.get(p, [])) if x]
    ids = set(statements) | {v for vs in statements.values() for v in vs if re.fullmatch(r"[QP]\d+", v or "")}
    names = _labels(ids, lang_list[0])
    pretty = {f"{p} {names.get(p, p)}": [f"{v} ({names[v]})" if v in names else v for v in vs]
              for p, vs in statements.items()}
    pick = lambda d: {l: d[l]["value"] for l in lang_list + ["en"] if l in d}
    return {
        "id": qid,
        "labels": pick(e.get("labels", {})),
        "descriptions": pick(e.get("descriptions", {})),
        "aliases": {l: [a["value"] for a in e.get("aliases", {}).get(l, [])] for l in lang_list if l in e.get("aliases", {})},
        "statements": pretty,
        "statement_count": sum(len(v) for v in claims.values()),
        "sitelinks": {k: v["title"] for k, v in e.get("sitelinks", {}).items()
                      if k in {f"{l}wiki" for l in lang_list} | {"enwiki", "commonswiki"}},
        "sitelink_count": len(e.get("sitelinks", {})),
    }


def missing_terms(qids: Iterable[str], lang: str) -> List[dict]:
    """Items lacking a label or description in `lang`, with the English ones for context."""
    ids = [q for q in dict.fromkeys(qids) if re.fullmatch(r"Q\d+", q)]
    ents = _get_entities(ids, "labels|descriptions", f"{lang}|en")
    out = []
    for q in ids:
        e = ents.get(q, {})
        lab, desc = e.get("labels", {}), e.get("descriptions", {})
        if lang not in lab or lang not in desc:
            out.append({"id": q, "missing": [k for k, d in (("label", lab), ("description", desc)) if lang not in d],
                        "en_label": lab.get("en", {}).get("value"), "en_description": desc.get("en", {}).get("value"),
                        "label": lab.get(lang, {}).get("value"), "description": desc.get(lang, {}).get("value")})
    return out


def search(text: str, lang: str = "en", limit: int = 7) -> List[dict]:
    data = api({"action": "wbsearchentities", "search": text, "language": lang,
                "uselang": lang, "type": "item", "limit": str(limit)}, site="wikidata")
    return [{"id": r["id"], "label": r.get("label"), "description": r.get("description")}
            for r in data.get("search", [])]


def properties(pids: Iterable[str], lang: str = "en") -> Dict[str, dict]:
    ids = [p for p in dict.fromkeys(pids) if re.fullmatch(r"P\d+", p)]
    ents = _get_entities(ids, "labels|datatype", f"{lang}|en") if ids else {}
    return {p: {"label": (e.get("labels", {}).get(lang) or e.get("labels", {}).get("en") or {}).get("value"),
                "datatype": e.get("datatype"), "exists": "missing" not in e}
            for p, e in ents.items()}


_QS_TERM = re.compile(r"^[LDAS][a-z\-]+$")


def check_quickstatements(text: str) -> dict:
    """
    Lint a QuickStatements (V1, tab-separated) batch before a human runs it.

    Checks that every item and property exists, that item-valued properties
    get items and string/term values are quoted, and flags statements that
    would duplicate one the item already has.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    rows, problems = [], []
    removals = set()
    for n, line in enumerate(lines, 1):
        if line.strip().upper() in ("CREATE", "MERGE"):
            continue
        parts = [p.strip() for p in (line.split("\t") if "\t" in line else line.split("|"))]
        if parts and parts[0].startswith("-"):
            parts[0] = parts[0][1:]
            removals.add(n)
        if len(parts) < 3:
            problems.append(f"line {n}: fewer than 3 columns")
            continue
        rows.append((n, parts))
    ent_id = re.compile(r"[QPLM]\d+(?:-[FS]\d+)?")
    ids = {p[0] for _, p in rows if ent_id.fullmatch(p[0]) and "-" not in p[0]}
    ids |= {p[2] for _, p in rows if re.fullmatch(r"Q\d+", p[2])}
    pids = {p[1] for _, p in rows if re.fullmatch(r"P\d+", p[1])}
    ents = _get_entities(sorted(ids), "claims|labels", "en") if ids else {}
    props = properties(pids)
    for n, (subj, pred, val, *rest) in rows:
        if subj != "LAST" and subj in ids and (subj not in ents or "missing" in ents.get(subj, {})):
            problems.append(f"line {n}: entity {subj} does not exist")
        if _QS_TERM.match(pred):
            if not (val.startswith('"') and val.endswith('"')):
                problems.append(f"line {n}: {pred} value must be quoted")
            continue
        info = props.get(pred)
        if not info or not info["exists"]:
            problems.append(f"line {n}: property {pred} does not exist")
            continue
        dt = info["datatype"]
        if val.lower() in ("somevalue", "novalue"):
            continue
        if dt == "wikibase-item" and not re.fullmatch(r"Q\d+", val):
            problems.append(f"line {n}: {pred} ({info['label']}) needs an item, got {val}")
        if dt in ("string", "external-id", "url") and not val.startswith('"'):
            problems.append(f"line {n}: {pred} ({info['label']}) value must be quoted")
        if dt == "time" and not re.fullmatch(r"[+-]\d{4,}-\d\d-\d\dT00:00:00Z/\d{1,2}", val):
            problems.append(f"line {n}: {pred} time must look like +1950-00-00T00:00:00Z/9")
        if n in removals:
            continue
        if dt == "wikibase-item" and subj in ents:
            have = {c["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
                    for c in ents[subj].get("claims", {}).get(pred, [])}
            if val in have:
                problems.append(f"line {n}: {subj} already has {pred} = {val} (duplicate)")
        if not any(r.startswith("S") for r in rest[::2]) and pred not in ("P31", "P279", "P18", "P373", "P910"):
            problems.append(f"line {n}: no source (S…) for {pred} — add a reference")
    return {"lines": len(lines), "problems": problems, "ok": not problems}


_YEAR = re.compile(r"(?<!\d)(\d{3,4})(?!\d)")


def infobox_vs_wikidata(wikitext: str, qid: str) -> List[dict]:
    """Birth/death years in the infobox that disagree with the item's P569/P570."""
    code = mwp.parse(wikitext)
    box = next((t for t in code.filter_templates() if "infobox" in str(t.name).lower()
                or "bilgiquti" in str(t.name).lower()), None)
    if box is None:
        return []
    claims = _get_entities([qid], "claims").get(qid, {}).get("claims", {})
    out = []
    for param, pid in (("birth_date", "P569"), ("death_date", "P570")):
        if not box.has(param):
            continue
        raw = re.sub(r"\d{1,4}\s*(?:AH|H)\b", "", str(box.get(param).value))
        years = set(_YEAR.findall(mwp.parse(raw).strip_code())) | set(re.findall(r"\|\s*(\d{3,4})\s*\|", raw))
        wd = {(_value(c["mainsnak"]) or "")[:4].lstrip("0") for c in claims.get(pid, [])}
        if years and wd and not (years & wd):
            out.append({"field": param, "infobox": sorted(years), "wikidata": sorted(wd), "property": pid})
    return out
