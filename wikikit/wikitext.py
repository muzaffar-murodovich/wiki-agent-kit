"""
wikikit/wikitext.py - Language-independent wikitext patterns and helpers.

Anything here must hold on every wiki. Language-specific rules (dates,
transliteration, heading names) live in a profile, never here.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable, List, Optional

import mwparserfromhell as mwp

REF_TAG = r"<ref(?:\s[^>]*)?(?<!/)>.*?</ref\s*>"
REF_SELF_CLOSING = r"<ref[^>]*/\s*>"
CITATION_TEMPLATE_NAME = r"^\s*(?:cite\b|citation\s*$)"
CITATION_TEMPLATE = r"\{\{\s*(?:cite\b|citation\b)[^{}]*\}\}"
CITATION_LINK_PARAM = r"^[a-z]+\d*-?link\d*$"
WIKILINK = r"\[\[([^\]\|]+)(?:\|([^\]]+))?\]\]"
HTML_COMMENT = r"<!--.*?-->"
EMPTY_PARAM = r"\|\s*([^=\|{}]+?)\s*=\s*(?=\n\s*[\|}])"
MULTIPLE_NEWLINES = r"\n\s*\n\s*\n+"
INVALID_TITLE_CHARS = r"[\[\]{}|<>#]"

# Placeholder protocol (see wikikit/translate.py)
REF_PLACEHOLDER = r"REF_[a-f0-9]{8}"
COMPRESSED_PLACEHOLDER = r"(?:REF|CITE)_[a-f0-9]{8}"
LINK_PLACEHOLDER = r"LNK\d+"
TRANSLATED_LINK_PLACEHOLDER = r"\[\[(LNK\d+)\|([^\]]*)\]\]"
BRACED_LINK_PLACEHOLDER = r"\{\{\s*((?:LNK|Q)\d+)\s*\|([^{}|]*)\}\}"
LEFTOVER_LINK_PLACEHOLDER = r"(?:\[\[|\{\{)\s*((?:LNK|Q)\d+)\s*[|\]}]"
CAT_TOKEN = r"⟦CAT:(Q\d+)\|([^|⟧]+)\|([^⟧]*)⟧"
CAT_TOKEN_ANY = r"⟦CAT:[^⟧]*⟧"

_REF_OR_CITATION = re.compile(
    REF_TAG + r"|" + REF_SELF_CLOSING + r"|" + CITATION_TEMPLATE, re.DOTALL | re.IGNORECASE
)


def remove_empty_params(wikitext: str) -> str:
    return re.sub(EMPTY_PARAM, "", wikitext)


def strip_comments(wikitext: str) -> str:
    return re.sub(HTML_COMMENT, "", wikitext, flags=re.DOTALL)


def collapse_newlines(wikitext: str) -> str:
    return re.sub(MULTIPLE_NEWLINES, "\n\n", wikitext)


def apply_outside_refs(wikitext: str, fix: Callable[[str], str]) -> str:
    """Apply a string fix to everything except references and citation templates."""
    saved: List[str] = []

    def mask(m: re.Match) -> str:
        saved.append(m.group(0))
        return f"\x00{len(saved) - 1}\x00"

    text = fix(_REF_OR_CITATION.sub(mask, wikitext))
    return re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m.group(1))], text)


def fold(text: str) -> str:
    """Case- and diacritic-insensitive form, for comparing two spellings."""
    nfkd = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).replace("ʻ", "'").replace("ʼ", "'")


def generic_same_name(target: str, label: str) -> bool:
    """
    Default label/target comparator: identical apart from case of the first
    letter and diacritics. Profiles may supply a smarter, language-aware one.
    """
    if label == target:
        return True
    if ":" in target or "(" in target:
        return False
    if not label[:1].isupper():
        return False
    return fold(target) == fold(label)


def generic_clean_title(text: Optional[str]) -> Optional[str]:
    """A model-written name made into a valid page title, or None."""
    if not text:
        return None
    name = re.sub(r"'{2,}", "", text)
    name = re.sub(r"\s+", " ", name).strip().strip('"«»“”')
    if not name or re.search(INVALID_TITLE_CHARS, name):
        return None
    return name[0].upper() + name[1:]


def refs_of(wikitext: str) -> List[str]:
    """Every reference (full and self-closing), in order."""
    return [m.group(0) for m in re.finditer(REF_TAG + "|" + REF_SELF_CLOSING, wikitext,
                                            re.DOTALL | re.IGNORECASE)]


def plain_text(wikitext: str) -> str:
    """Readable prose without markup, refs or templates."""
    no_refs = re.sub(REF_TAG + "|" + REF_SELF_CLOSING, "", wikitext, flags=re.DOTALL | re.IGNORECASE)
    return mwp.parse(no_refs).strip_code(normalize=True, collapse=True)
