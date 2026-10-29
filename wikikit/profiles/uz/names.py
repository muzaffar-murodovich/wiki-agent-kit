#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
link_labels.py - Wikilink label cleanup (translation_rules.md rule 2)

A wikilink target is resolved from Wikidata while its label comes from the
translation model, so the two regularly disagree on the spelling of the same
name: [[Lohur|Lahor]]. Rule 2 wants them to agree.

Only the pipe of a label that is the *same name* spelled differently may be
dropped. A label that is a different word carries the sentence grammar and
must stay: [[Somalilar|somalilik]] collapsed to [[Somalilar]] breaks the text.
Everything this module cannot judge mechanically is reported instead, so the
violation shows up in the run log rather than staying silent.
"""

import re
from typing import List, Optional, Tuple

from wikikit.profiles.uz.rules import RegexPatterns, apply_outside_refs, transliterate_name

# Characters that carry no weight when comparing two spellings of a name:
# the Uzbek letters ʻ/ʼ, apostrophes, hyphens and spaces. The typographic
# quotes ‘/’ are included: the model writes them for ʻ/ʼ, Vikifikator turns
# them back on save, and until then [[Qurʼon|Qur’on]] is one name.
_INSIGNIFICANT = str.maketrans({c: "" for c in "ʻʼ‘’'`- "})

# The Arabic nisba ending is spelt -iy or -i: al-Qoriy / al-Qori.
_NISBA_IY = re.compile(r"iy\b")

# A "y" closing a syllable is a vowel glide: Oysha / Oisha.
_GLIDE_Y = re.compile(r"(?<=[aeiou])y(?![aeiou])")

# Every vowel folds to one symbol, so only the consonant skeleton is compared.
# This is what separates a re-spelling (Lohur/Lahor) from a different name.
_VOWELS = str.maketrans({c: "V" for c in "aeiou"})

# The Arabic definite article and its assimilated forms are not part of the
# name: "Abu al-Faraj al-Isfahoniy" and "Abulfaraj Isfahoniy" are one person.
_ARTICLE = re.compile(r'\b(?:al|ad|ar|as|az|at|an|ash)[- ]', re.IGNORECASE)

_WIKILINK = re.compile(RegexPatterns.WIKILINK)

# A label wholly in italics or bold: ''Kitob al-Kofiy''
_WRAPPED_LABEL = re.compile(r"('{2,3})(.+?)\1")

_INVALID_TITLE = re.compile(RegexPatterns.INVALID_TITLE_CHARS)


def _normalize(name: str) -> str:
    """Strip everything that two spellings of one name may legitimately differ in."""
    name = _ARTICLE.sub("", name.casefold())
    name = name.replace("abul", "abu")
    name = _NISBA_IY.sub("i", name)
    return name.translate(_INSIGNIFICANT)


def _skeleton(name: str) -> str:
    """Consonant skeleton of a name: vowels folded, insignificant chars gone."""
    return _GLIDE_Y.sub("i", _normalize(name)).translate(_VOWELS)


def is_same_name(target: str, label: str) -> bool:
    """
    True when the label is the same name as the target, only spelled differently.

    Deliberately strict — a wrong collapse silently corrupts a sentence, while
    a missed one is only an unfixed link that gets reported.

    >>> is_same_name("Lohur", "Lahor")
    True
    >>> is_same_name("Somalilar", "somalilik")
    False
    """
    if label == target:
        return True

    # A namespace or interwiki prefix (File:, Turkum:, :fa:) is not a name.
    if ":" in target:
        return False

    # Rule 2 keeps the label of a parenthetical disambiguator: [[Kordova (shahar)|Kordova]]
    if "(" in target or "(" in label:
        return False

    # A lowercase label is a common-noun gloss, not a name: [[Tasavvuf|soʻfiy]]
    if not (target[:1].isupper() and label[:1].isupper()):
        return False

    # A different length means a different word form: [[Oʻn ikki imom|Oʻn ikki imomiy]]
    if len(_normalize(target)) != len(_normalize(label)):
        return False

    return _skeleton(target) == _skeleton(label)


def _is_reportable(target: str, label: str) -> bool:
    """
    True when a kept pipe is a name/name disagreement a human should look at.

    A lowercase gloss and the exceptions rule 2 grants (namespace prefix,
    parenthetical disambiguator) are correct as they are and stay out of the
    report, so the list holds only real work.
    """
    return ":" not in target and "(" not in target and label[:1].isupper()


def collapse_redundant_labels(wikitext: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Drop the pipe of every label that only re-spells its target.

    Uzbek case suffixes sit outside the brackets, so the collapse leaves the
    sentence intact: [[Lohur|Lahor]]ga -> [[Lohur]]ga ("Lohurga").

    Args:
        wikitext: finalized wikitext

    Returns:
        (cleaned wikitext, remaining target/label mismatches to check by hand)
    """
    mismatched: List[Tuple[str, str]] = []

    def replacer(match: re.Match) -> str:
        target, label = match.group(1), match.group(2)
        if not label:
            return match.group(0)

        target_clean, label_clean = target.strip(), label.strip()
        if is_same_name(target_clean, label_clean):
            return f"[[{target_clean}]]"

        # A book title keeps its italics outside the link: [[X|''X'']] -> ''[[X]]''
        wrapped = _WRAPPED_LABEL.fullmatch(label_clean)
        if wrapped and is_same_name(target_clean, wrapped.group(2).strip()):
            quotes = wrapped.group(1)
            return f"{quotes}[[{target_clean}]]{quotes}"

        # Not mechanically decidable — leave it alone and hand it to a human.
        if _is_reportable(target_clean, label_clean):
            mismatched.append((target_clean, label_clean))
        return match.group(0)

    # References are left alone: their links show the source's own English
    # name on purpose ([[Lohur|Lahore]]), and collapsing one would rewrite
    # what the citation quotes.
    cleaned = apply_outside_refs(wikitext, lambda text: _WIKILINK.sub(replacer, text))
    # One line per distinct link — the same link repeats across an article.
    return cleaned, list(dict.fromkeys(mismatched))


def clean_page_title(text: Optional[str]) -> Optional[str]:
    """
    Turn a model-written name into something usable as a page name.

    A label can carry what a page name must not: italics (''Kitāb al Kāfī''),
    diacritics that translation_rules.md rule 2a removes, a lowercase first
    letter. None when nothing usable is left.
    """
    if not text:
        return None
    name = re.sub(r"'{2,}", "", text)
    name = transliterate_name(re.sub(r"\s+", " ", name).strip())
    if not name or _INVALID_TITLE.search(name):
        return None
    return name[0].upper() + name[1:]
