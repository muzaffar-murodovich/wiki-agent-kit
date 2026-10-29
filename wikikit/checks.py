"""
wikikit/checks.py - What a reviewer must look at before publishing.

Nothing here edits text. Each check answers a question a human would
otherwise have to answer by reading wikitext:

  * Did any reference disappear, or appear from nowhere?  (a new <ref> or URL
    that is not in the source is the signature of a hallucinated citation)
  * Did a number change?  (years, counts, measurements: a mistranslated
    number reads fluently and is the hardest error to spot)
  * Is the markup balanced?  ([[ ]] {{ }} and <ref></ref>)
  * Did a placeholder survive?
  * Language-specific checks from the target profile.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

from wikikit.wikitext import REF_SELF_CLOSING, REF_TAG, plain_text

_URL = re.compile(r"https?://[^\s|\]}<>\"']+")
_NUMBER = re.compile(r"(?<![\w.,])\d{2,}(?:[.,]\d+)?(?![\w])")
_NON_PROSE_LINE = re.compile(r"^\s*(?:\[\[[^\[\]]+:[^\[\]]*\]\]\s*)+$|⟦CAT:[^⟧]*⟧", re.M)
_REF_NAME = re.compile(r"""<ref\s[^>]*name\s*=\s*["']?([^"'/>]+?)["']?\s*/?>""", re.I)


def _refs(text: str) -> List[str]:
    return re.findall(REF_TAG, text, re.DOTALL | re.IGNORECASE)


def reference_check(source: str, final: str) -> Dict[str, object]:
    src_urls = set(_URL.findall(source))
    fin_urls = set(_URL.findall(final))
    src_named = set(_REF_NAME.findall(source))
    fin_named = set(_REF_NAME.findall(final))
    fin_defined = {m for r in _refs(final) for m in _REF_NAME.findall(r)}
    invoked = {m.group(1) for m in re.finditer(r"""<ref\s[^>]*name\s*=\s*["']?([^"'/>]+?)["']?\s*/\s*>""", final, re.I)}
    return {
        "source_refs": len(_refs(source)) + len(re.findall(REF_SELF_CLOSING, source, re.I)),
        "final_refs": len(_refs(final)) + len(re.findall(REF_SELF_CLOSING, final, re.I)),
        "new_urls": sorted(fin_urls - src_urls),            # must be empty
        "lost_urls": sorted(src_urls - fin_urls),
        "new_ref_names": sorted(fin_named - src_named),
        "undefined_named_refs": sorted(invoked - fin_defined),   # "Cite error" on the wiki
    }


def _normalise_digits(text: str) -> str:
    """Native digits (۱۹۵۰, १९५०) to ASCII, and thousands separators removed."""
    import unicodedata
    text = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in text)
    # A separator followed by exactly three digits groups thousands, in any
    # locale's style: 1,234,567 / 1.234.567 / 1 234 567. ("1,5" stays a decimal.)
    return re.sub(r"(?<=\d)[,.\u00a0\u2009\u202f '](?=\d{3}(?!\d))", "", text)


def number_check(source: str, final: str) -> Dict[str, List[str]]:
    """Numbers in the prose of one text but not the other (citations excluded)."""
    def nums(t: str) -> Counter:
        # Category and file lines are not prose: "760s deaths" is not a claim.
        t = _NON_PROSE_LINE.sub("", t)
        t = _normalise_digits(plain_text(t))
        return Counter(n.replace(",", "").replace(".", "") for n in _NUMBER.findall(t))
    s, f = nums(source), nums(final)
    return {"missing_in_translation": sorted((s - f).elements()),
            "not_in_source": sorted((f - s).elements())}


def markup_check(final: str) -> List[str]:
    problems = []
    pairs = [("[[", "]]"), ("{{", "}}")]
    for o, c in pairs:
        if final.count(o) != final.count(c):
            problems.append(f"unbalanced {o} {c}: {final.count(o)} vs {final.count(c)}")
    opens = len(re.findall(r"<ref(?:\s[^>]*)?(?<!/)>", final, re.I))
    closes = len(re.findall(r"</ref\s*>", final, re.I))
    if opens != closes:
        problems.append(f"unbalanced <ref>: {opens} opened, {closes} closed")
    if re.search(r"⟦|⟧|\{\{\s*TPL:|\[\[\s*(?:Q|LNK)\d+\s*[|\]]", final):
        problems.append("placeholder left in text")
    return problems


def has_bold_lead(final: str) -> bool:
    """A line of prose (not inside a template) opening with the bold subject name."""
    return bool(re.search(r"^[^|{}\n]*'''[^'\n]+'''", final, re.M))


def run(source: str, final: str, meta: dict, target_profile) -> Dict[str, object]:
    refs = reference_check(source, final)
    nums = number_check(source, final)
    markup = markup_check(final)
    lang_warnings = target_profile.check_output(final, meta.get("title", ""))
    if not has_bold_lead(final):
        lang_warnings = ["no bold subject name at the start of a prose line"] + lang_warnings
    blocking = []
    if refs["new_urls"]:
        blocking.append("URL(s) in the translation that are not in the source")
    if refs["undefined_named_refs"]:
        blocking.append("named reference(s) used but never defined")
    if markup:
        blocking.extend(markup)
    return {
        "blocking": blocking,
        "references": refs,
        "numbers": nums,
        "language": lang_warnings,
    }


def summarize(report: dict) -> Dict[str, object]:
    c = report.get("checks", {})
    return {
        "templates_without_target": report.get("templates", {}).get("kept_without_target", []),
        "blocking": c.get("blocking", []),
        "numbers_to_verify": len(c.get("numbers", {}).get("missing_in_translation", []))
                             + len(c.get("numbers", {}).get("not_in_source", [])),
        "language_warnings": len(c.get("language", [])),
        "label_mismatches": len(report.get("label_mismatches", [])),
        "links_left_in_source_language": len(report.get("links", {}).get("left_in_source_language", [])),
        "leftover_placeholders": report.get("leftover_placeholders", []),
    }
