"""
wikikit/trimmer.py - Reduce a long article to lead + citation apparatus.

A 40 KB biography costs as much to translate as it does to review, and the
body sections are the part a small-wiki stub does not need yet. trim_article()
keeps the lead paragraph, the references section and the categories, and
drops everything in between.

The section split is done with mwparserfromhell, not regex, because "=="
also appears inside <ref> bodies and template parameters, where it is not a
heading at all. The parser already knows the difference.
"""

import re
from typing import Dict, List, Optional, Tuple

import mwparserfromhell as mwp


# Injected when the kept text cites references but has nowhere to render
# them. Written in the source language on purpose: it goes through
# translation like every other heading.
_REFLIST_SECTION = "\n\n== References ==\n{{reflist}}\n"

_HAS_REFLIST = re.compile(r'\{\{\s*(?:reflist|refs)\b|<\s*references', re.IGNORECASE)


def _heading_title(section) -> str:
    """The plain text of a section's own heading ('' for the lead)."""
    headings = section.filter_headings()
    if not headings:
        return ""
    # A level-2 section contains its level-3 children, so its own heading is
    # always the first one.
    return str(headings[0].title).strip()


DEFAULT_APPARATUS = (
    r"^\s*(?:references?|sources?|notes?|footnotes?|citations?"
    r"|works\s+cited|bibliography|further\s+reading|external\s+links)\s*$"
)
MULTIPLE_NEWLINES = r"\n\s*\n\s*\n+"


def _is_apparatus(title: str, apparatus: str = DEFAULT_APPARATUS) -> bool:
    """Is this heading the start of the references/links apparatus?"""
    # Strip markup first: some articles write == '''References''' == or
    # hang a wikilink in the heading.
    plain = mwp.parse(title).strip_code().strip()
    return bool(re.match(apparatus, plain, re.IGNORECASE))


def _ref_name(node) -> Optional[str]:
    """The name= attribute of a <ref> tag, or None."""
    for attr in node.attributes:
        if str(attr.name).strip().lower() == "name":
            return str(attr.value).strip().strip('"\'')
    return None


def _collect_ref_definitions(text: str) -> Dict[str, str]:
    """{name: full <ref name=...>...</ref>} for every named, non-empty ref."""
    defs: Dict[str, str] = {}
    for node in mwp.parse(text).filter_tags(
        matches=lambda n: str(n.tag).lower() == "ref"
    ):
        if node.self_closing:
            continue
        name = _ref_name(node)
        if name and name not in defs:
            defs[name] = str(node)
    return defs


def _inline_orphan_refs(kept: str, defs: Dict[str, str]) -> Tuple[str, List[str]]:
    """
    Give every <ref name="x"/> in `kept` a definition.

    A named ref is very often defined in a body section and only invoked in
    the lead. Cutting the body would leave uz.wiki rendering a red
    "Cite error: The named reference x was invoked but never defined", which
    the reviewer - reading Uzbek prose, not wikitext - would not catch.
    """
    defined = set(_collect_ref_definitions(kept))
    inlined: List[str] = []

    for node in mwp.parse(kept).filter_tags(
        matches=lambda n: str(n.tag).lower() == "ref"
    ):
        if not node.self_closing:
            continue
        name = _ref_name(node)
        if not name or name in defined or name not in defs:
            continue
        # Only the FIRST invocation carries the definition; later ones stay
        # short, exactly as the source article had them.
        kept = kept.replace(str(node), defs[name], 1)
        defined.add(name)
        inlined.append(name)

    return kept, inlined


def _rescue_categories(cut_text: str, kept: str) -> Tuple[List[str], bool]:
    """
    Categories and DEFAULTSORT found in the cut region but missing from kept.

    Normally the whole category block sits below == References == and is
    already inside `kept`. This keeps that assumption from being
    load-bearing.
    """
    found: List[str] = []
    code = mwp.parse(cut_text)

    for link in code.filter_wikilinks():
        if str(link.title).strip().lower().startswith("category:"):
            text = str(link)
            if text not in kept and text not in found:
                found.append(text)

    for tpl in code.filter_templates():
        if str(tpl.name).strip().upper().startswith("DEFAULTSORT"):
            text = str(tpl)
            if text not in kept and text not in found:
                found.append(text)

    has_defaultsort = any(f.startswith("{{") for f in found)
    return found, has_defaultsort


def trim_article(wikitext: str, apparatus: str = DEFAULT_APPARATUS,
                 min_lead_bytes: int = 400) -> Tuple[str, dict]:
    """
    Reduce a long article to lead + citation apparatus + categories.

    `apparatus` matches the SOURCE wiki's reference-section headings (from
    its profile: "source.apparatus_heading").

    Returns (text, info). When info["trimmed"] is False the text is returned
    unchanged and info["reason"] says why - the caller should fall back to a
    full translation rather than treating it as an error.
    """
    info = {
        "trimmed": False,
        "reason": "",
        "original_size": len(wikitext),
        "trimmed_size": len(wikitext),
        "kept_from": None,
        "cut_sections": [],
        "refs_inlined": [],
        "categories_recovered": 0,
        "reflist_added": False,
        "thin_lead": False,
    }

    code = mwp.parse(wikitext)
    sections = code.get_sections(levels=[2], include_lead=True, include_headings=True)

    if len(sections) <= 1:
        # Some articles use === for everything; try that before giving up.
        sections = code.get_sections(levels=[3], include_lead=True, include_headings=True)
    if len(sections) <= 1:
        info["reason"] = "no_sections"
        return wikitext, info

    lead = str(sections[0])

    # The apparatus is the LAST run of apparatus headings, not the first one:
    # a prose section can carry the same name. "Isma'il ibn Ja'far" opens its
    # body with "== Sources ==" on the reliability of the sources, and taking
    # that as the references sent the whole 31 KB article to translation.
    anchor = None
    for i in range(len(sections) - 1, 0, -1):
        if _is_apparatus(_heading_title(sections[i]), apparatus):
            anchor = i
        elif anchor is not None:
            break

    if anchor is None:
        cut = sections[1:]
        tail = ""
        info["reason"] = "no_apparatus_heading"
    elif anchor == 1:
        # Lead is followed straight by References - there is no body to cut.
        info["reason"] = "nothing_to_cut"
        return wikitext, info
    else:
        cut = sections[1:anchor]
        tail = "".join(str(s) for s in sections[anchor:])
        info["kept_from"] = mwp.parse(_heading_title(sections[anchor])).strip_code().strip()

    cut_text = "".join(str(s) for s in cut)
    info["cut_sections"] = [
        mwp.parse(_heading_title(s)).strip_code().strip() for s in cut
    ]

    kept = lead.rstrip() + ("\n\n" + tail.lstrip() if tail.strip() else "")

    kept, inlined = _inline_orphan_refs(kept, _collect_ref_definitions(wikitext))
    info["refs_inlined"] = inlined

    if "<ref" in kept and not _HAS_REFLIST.search(kept):
        kept = kept.rstrip() + _REFLIST_SECTION
        info["reflist_added"] = True

    rescued, _ = _rescue_categories(cut_text, kept)
    if rescued:
        kept = kept.rstrip() + "\n\n" + "\n".join(rescued) + "\n"
        info["categories_recovered"] = len(rescued)

    kept = re.sub(MULTIPLE_NEWLINES, "\n\n", kept).strip() + "\n"

    info["trimmed"] = True
    info["trimmed_size"] = len(kept)
    info["thin_lead"] = len(lead.strip()) < min_lead_bytes

    return kept, info
