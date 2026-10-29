"""
Uzbek (uz.wikipedia) profile hooks.

Everything here was proven in production in wikipedia-translator, which
translated and published uz.wiki articles daily: the regex fixes (dates,
AH/CE, -lik suffix, Arabic transliteration, punctuation around references),
the name comparator behind rule 2 of the style guide, and the output checks.
"""

from typing import List, Optional

from wikikit.profiles.uz import checks, names, rules


def post_process(text: str) -> str:
    return rules.apply_all_fixes(text)


def same_name(target: str, label: str) -> bool:
    return names.is_same_name(target, label)


def clean_title(text: Optional[str]) -> Optional[str]:
    return names.clean_page_title(text)


def check_output(text: str, title: str) -> List[str]:
    return checks.check_output(text, title)


def check_source(wikitext: str) -> List[str]:
    return checks.check_source(wikitext)
