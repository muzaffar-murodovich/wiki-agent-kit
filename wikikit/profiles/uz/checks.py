#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
utils/source_checks.py - Warnings the pipeline cannot fix, for the human.

Some defects in a finished article are not the pipeline's doing: the en.wiki
source already had them, and a faithful translation carries them over. The
2026-09-16 batch shipped three such articles — reference text with Arabic
letters inside Latin words, a short description and an infobox disagreeing on
a birth year, a birth category contradicting the infobox. Nothing here edits
the text; it only says where to look.

One check reads the output instead: a bold lead name still spelled in English.
"""

import re
from typing import Iterable, List, Optional, Set

from wikikit.profiles.uz.rules import RegexPatterns, clean_html_comments

_MIXED = re.compile(RegexPatterns.MIXED_SCRIPT_WORD)
_SHORT_DESC = re.compile(RegexPatterns.SHORT_DESCRIPTION, re.IGNORECASE)
_YEAR_RANGE = re.compile(RegexPatterns.YEAR_RANGE)
_INFOBOX_DATE = re.compile(RegexPatterns.INFOBOX_DATE, re.IGNORECASE | re.MULTILINE)
_HIJRI_YEAR = re.compile(RegexPatterns.HIJRI_YEAR)
_YEAR_CATEGORY = re.compile(RegexPatterns.YEAR_CATEGORY, re.IGNORECASE)
_ENGLISH_SPELLING = re.compile(RegexPatterns.ENGLISH_SPELLING, re.IGNORECASE)
_YEAR = re.compile(r'(?<!\d)\d{3,4}(?!\d)')
_LEAD_LINE = re.compile(RegexPatterns.LEAD_LINE, re.MULTILINE)
_LEAD_NOISE = re.compile(RegexPatterns.LEAD_NOISE, re.DOTALL)

_EVENT = {"birth": "tugʻilgan", "death": "vafot etgan"}


def mixed_script_words(wikitext: str) -> List[str]:
    """Latin words with Arabic letters glued on, deduplicated, in text order."""
    return list(dict.fromkeys(_MIXED.findall(wikitext)))


def _infobox_years(wikitext: str) -> dict:
    """{"birth": {...}, "death": {...}} — Gregorian years in the infobox dates."""
    years = {"birth": set(), "death": set()}
    for kind, value in _INFOBOX_DATE.findall(wikitext):
        value = _HIJRI_YEAR.sub(" ", value)
        years[kind.lower()].update(int(y) for y in _YEAR.findall(value))
    return years


def _matches(year: int, decade: bool, known: Set[int]) -> bool:
    if decade:
        return any(k // 10 == year // 10 for k in known)
    return year in known


def _describe(years: Iterable[int]) -> str:
    return "/".join(str(y) for y in sorted(years))


def year_conflicts(wikitext: str) -> List[str]:
    """
    Birth and death years that the source states in two different ways.

    The infobox is the reference: the short description's year range and the
    "NNNN births" / "NNNNs deaths" categories are compared against it. A
    Hijri year is ignored, so "255 AH / 868 CE" is only 868.
    """
    # An empty |death_date= often holds the template's instructions in a
    # comment, example years included: "...|1908|31|8|1967|28|2}}" (Raja ibn Haywa).
    wikitext = clean_html_comments(wikitext)
    infobox = _infobox_years(wikitext)
    conflicts = []

    desc = _SHORT_DESC.search(wikitext)
    rng = _YEAR_RANGE.search(desc.group(1)) if desc else None
    if rng:
        for kind, year in (("birth", int(rng.group(1))), ("death", int(rng.group(2)))):
            if infobox[kind] and year not in infobox[kind]:
                conflicts.append(
                    f"{_EVENT[kind]} yili: qisqa tavsifda {year}, "
                    f"bilgiqutida {_describe(infobox[kind])}"
                )

    for year, decade, event in _YEAR_CATEGORY.findall(wikitext):
        kind = "birth" if event.lower() == "births" else "death"
        if infobox[kind] and not _matches(int(year), bool(decade), infobox[kind]):
            conflicts.append(
                f"{_EVENT[kind]} yili: kategoriyada {year}{decade}, "
                f"bilgiqutida {_describe(infobox[kind])}"
            )

    return list(dict.fromkeys(conflicts))


def english_subject_name(result: str, title: Optional[str]) -> Optional[str]:
    """The English page title, when it survived as the bold lead name."""
    if not title:
        return None
    name = re.sub(r'\s*\([^)]*\)$', '', title).strip()
    if not _ENGLISH_SPELLING.search(name):
        # "Ahmad Bamba" is spelled the same in Uzbek; nothing to tell apart.
        return None
    return name if f"'''{name}'''" in result else None


def lead_lacks_dash(result: str) -> bool:
    """
    True when the lead sentence has no em-dash after the name and its bracket.

    translation_rules.md rule 1 wants "'''Ism''' (maʼlumotlar) — taʼrif". The
    model sometimes keeps the English comma style instead, and since Phase 5
    is gone nothing else would notice.
    """
    line = _LEAD_LINE.search(result)
    if not line:
        return False
    text = line.group(0)
    # Nested templates come off from the inside out.
    while True:
        stripped = _LEAD_NOISE.sub("", text)
        if stripped == text:
            break
        text = stripped

    name_end = text.find("'''", 3)
    if name_end < 0:
        return False
    rest = text[name_end + 3:].lstrip()
    if rest.startswith("("):
        depth = 0
        for i, ch in enumerate(rest):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0:
                rest = rest[i + 1:]
                break
    sentence = rest.split(". ", 1)[0]
    return "—" not in sentence


def check_source(wikitext: str) -> List[str]:
    """Human-readable warnings about defects inherited from the source."""
    warnings = []
    mixed = mixed_script_words(wikitext)
    if mixed:
        warnings.append(
            "Manbada lotin soʻziga arab harfi yopishgan (asl maqoladagi xato): "
            + ", ".join(mixed)
        )
    warnings.extend(f"Manbada yil ziddiyati — {c}" for c in year_conflicts(wikitext))
    return warnings


def check_output(result: str, title: Optional[str]) -> List[str]:
    """Human-readable warnings about the translated text itself."""
    warnings = []
    name = english_subject_name(result, title)
    if name:
        warnings.append(
            f"Maqola nomi inglizcha qolgan: '''{name}''' — oʻzbekcha transliteratsiya qiling"
        )
    if lead_lacks_dash(result):
        warnings.append("Kirish jumlasi 1-qoidaga mos emas: nom va qavsdan keyin «—» yoʻq")
    return warnings
