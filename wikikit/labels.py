"""
wikikit/labels.py - Drop link labels that only re-spell their target.

A link target comes from Wikidata, its label from the translator, so the two
regularly spell one name differently: [[Lohur|Lahor]]. Only a label that is
the *same name* may lose its pipe; a label that is a different word carries
sentence grammar and must stay ([[Somalilar|somalilik]]).

Whether two strings are "the same name" is language-specific, so the
comparator comes from the target profile (uz has a consonant-skeleton
comparator built for Arabic names; the generic one only ignores case and
diacritics). Everything it cannot decide is reported, never guessed.
"""

from __future__ import annotations

import re
from typing import Callable, List, Tuple

from wikikit.wikitext import WIKILINK, apply_outside_refs

_WIKILINK = re.compile(WIKILINK)
_WRAPPED = re.compile(r"('{2,3})(.+?)\1")


def collapse(wikitext: str, same_name: Callable[[str, str], bool]) -> Tuple[str, List[Tuple[str, str]]]:
    """(cleaned text, remaining target/label pairs a human should look at)."""
    mismatched: List[Tuple[str, str]] = []

    def repl(m: re.Match) -> str:
        target, label = m.group(1), m.group(2)
        if not label:
            return m.group(0)
        t, lab = target.strip(), label.strip()
        if same_name(t, lab):
            return f"[[{t}]]"
        wrapped = _WRAPPED.fullmatch(lab)
        if wrapped and same_name(t, wrapped.group(2).strip()):
            q = wrapped.group(1)
            return f"{q}[[{t}]]{q}"
        if ":" not in t and "(" not in t and lab[:1].isupper():
            mismatched.append((t, lab))
        return m.group(0)

    # Citation links show the source's own name on purpose: leave them be.
    cleaned = apply_outside_refs(wikitext, lambda s: _WIKILINK.sub(repl, s))
    return cleaned, list(dict.fromkeys(mismatched))
