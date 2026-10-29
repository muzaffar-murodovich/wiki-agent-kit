"""
wikikit/profiles - Per-language knowledge, kept out of the code.

A profile is a directory named after the wiki's language code:

    profile.json        required: namespaces, fallbacks, attribution wording
    style.md            the translation style guide the translator agent reads
    localization.json   optional: {literal text: replacement}, one pass after finalize
    fixers.py           optional: Python hooks, any of
                          post_process(text) -> text
                          same_name(target, label) -> bool
                          clean_title(text) -> str | None
                          check_output(text, title) -> list[str]
                          check_source(source_wikitext) -> list[str]

Built-in profiles ship inside the package. A user's own profiles live in
$WIKIKIT_HOME/profiles/<lang>/ and win over the built-in ones, so a
community can write a profile without forking the kit (the new-profile
skill drafts one).

A language with no profile still works: links, categories, templates and
references are mapped through Wikidata, and the generic comparator and title
cleaner are used. A profile only makes the result better.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, List, Optional, Tuple

from wikikit.wikitext import generic_clean_title, generic_same_name

BUILTIN_DIR = Path(__file__).parent
HOOKS = ("post_process", "same_name", "clean_title", "check_output", "check_source")


def home() -> Path:
    """Where jobs, queues and user profiles live (default ~/WikiWork)."""
    from wikikit.api import setting
    raw = setting("WIKIKIT_HOME")
    return Path(raw).expanduser() if raw else Path.home() / "WikiWork"


def _profile_dir(lang: str) -> Optional[Path]:
    for base in (home() / "profiles", BUILTIN_DIR):
        d = base / lang
        if (d / "profile.json").is_file():
            return d
    return None


@dataclass
class Profile:
    lang: str
    data: dict = field(default_factory=dict)
    directory: Optional[Path] = None
    module: Optional[ModuleType] = None
    replacements: Optional[Tuple[re.Pattern, Dict[str, str]]] = None

    # ---- data -----------------------------------------------------------
    @property
    def name(self) -> str:
        return self.data.get("name", self.lang)

    @property
    def category_ns(self) -> str:
        return self.data.get("namespaces", {}).get("category", "Category")

    @property
    def template_fallbacks(self) -> Dict[str, str]:
        return {k.lower(): v for k, v in self.data.get("template_fallbacks", {}).items()}

    @property
    def drop_unmapped_templates(self) -> bool:
        """Remove a template with no counterpart on the target wiki (default), or keep it."""
        return self.data.get("unmapped_templates", "drop") == "drop"

    @property
    def style_path(self) -> Optional[Path]:
        if self.directory and (self.directory / "style.md").is_file():
            return self.directory / "style.md"
        return None

    def attribution(self) -> dict:
        return self.data.get("attribution", {})

    # ---- hooks with generic fallbacks ------------------------------------
    def _hook(self, name: str) -> Optional[Callable]:
        return getattr(self.module, name, None) if self.module else None

    def same_name(self, target: str, label: str) -> bool:
        h = self._hook("same_name")
        return h(target, label) if h else generic_same_name(target, label)

    def clean_title(self, text: Optional[str]) -> Optional[str]:
        h = self._hook("clean_title")
        return h(text) if h else generic_clean_title(text)

    def post_process(self, text: str) -> str:
        h = self._hook("post_process")
        return h(text) if h else text

    def check_output(self, text: str, title: str) -> List[str]:
        h = self._hook("check_output")
        return list(h(text, title)) if h else []

    def check_source(self, wikitext: str) -> List[str]:
        h = self._hook("check_source")
        return list(h(wikitext)) if h else []

    @property
    def trim_threshold(self) -> int:
        return int(self.data.get("trim", {}).get("threshold_bytes", 10000))

    @property
    def trim_min_lead(self) -> int:
        return int(self.data.get("trim", {}).get("min_lead_bytes", 400))

    def source_setting(self, key: str, default: str) -> str:
        """Settings this wiki needs when it is the SOURCE of a translation."""
        return self.data.get("source", {}).get(key, default)

    def localize(self, text: str) -> Tuple[str, int]:
        if not self.replacements:
            return text, 0
        pattern, mapping = self.replacements
        count = 0

        def repl(m: re.Match) -> str:
            nonlocal count
            count += 1
            return mapping[m.group(0)]

        return pattern.sub(repl, text), count

    def summary(self) -> dict:
        return {
            "lang": self.lang, "name": self.name,
            "directory": str(self.directory) if self.directory else None,
            "style_guide": str(self.style_path) if self.style_path else None,
            "localization_rules": len(self.replacements[1]) if self.replacements else 0,
            "hooks": [h for h in HOOKS if self._hook(h)],
            "category_namespace": self.category_ns,
            "template_fallbacks": len(self.template_fallbacks),
        }


def _load_module(path: Path, lang: str) -> Optional[ModuleType]:
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"wikikit_profile_{lang}", path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _compile_replacements(mapping: Dict[str, str]) -> Optional[Tuple[re.Pattern, Dict[str, str]]]:
    """
    One alternation of the literal keys, longest first, applied in a single
    pass: "See also" wins over "See", and a replacement is never re-matched
    by a later rule. This is exactly how wikipedia-translator applied its map.
    """
    if not mapping:
        return None
    keys = sorted(mapping, key=len, reverse=True)
    return re.compile("|".join(re.escape(k) for k in keys)), dict(mapping)


_CACHE: Dict[str, Profile] = {}


def load(lang: str) -> Profile:
    """The profile for `lang`, or an empty generic one."""
    if lang in _CACHE:
        return _CACHE[lang]
    d = _profile_dir(lang)
    if d is None:
        prof = Profile(lang=lang)
    else:
        data = json.loads((d / "profile.json").read_text(encoding="utf-8"))
        loc = d / data.get("localization", "localization.json")
        mapping = json.loads(loc.read_text(encoding="utf-8")) if loc.is_file() else {}
        prof = Profile(lang=lang, data=data, directory=d,
                       module=_load_module(d / "fixers.py", lang),
                       replacements=_compile_replacements(mapping))
    _CACHE[lang] = prof
    return prof


def available() -> List[str]:
    langs = set()
    for base in (BUILTIN_DIR, home() / "profiles"):
        if base.is_dir():
            langs |= {p.name for p in base.iterdir() if (p / "profile.json").is_file()}
    return sorted(langs)


def clear_cache() -> None:
    _CACHE.clear()
