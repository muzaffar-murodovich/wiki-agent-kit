"""
wikikit/cite.py - Does the cited source actually say that?

The single most damaging AI failure on a wiki is a fluent sentence with a
real-looking citation that does not support it. This module does the
mechanical half of verification:

  claims()        every sentence that carries a reference, with that
                  reference's URL / title / quote
  fetch_text()    the readable text of a cited web page
  passages()      the few paragraphs of that text most likely to bear on
                  the claim (cheap lexical ranking, so the judging model
                  reads 3 short passages, not a whole page)

The judgment — supports / contradicts / says nothing — is made by Claude (the
cite-checker agent) or, when TYPESAFE_API_KEY is set, by Jev, which returns
a calibrated confidence so only the uncertain cases reach a human.
"""

from __future__ import annotations

import html
import re
import urllib.request
from typing import Dict, List

import mwparserfromhell as mwp

from wikikit.api import _SSL, user_agent
from wikikit.wikitext import REF_SELF_CLOSING, REF_TAG

_URL = re.compile(r"https?://[^\s|\]}<>\"']+")
_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁʻ'\"“\[])")


def _ref_details(ref: str) -> dict:
    code = mwp.parse(ref)
    d: Dict[str, str] = {}
    for tpl in code.filter_templates():
        for k in ("url", "title", "quote", "website", "work", "publisher", "author", "last", "date", "year", "page", "pages", "isbn", "doi"):
            if tpl.has(k) and str(tpl.get(k).value).strip():
                d.setdefault(k, mwp.parse(str(tpl.get(k).value)).strip_code().strip())
    if "url" not in d:
        m = _URL.search(ref)
        if m:
            d["url"] = m.group(0)
    if not d:
        d["text"] = mwp.parse(re.sub(r"</?ref[^>]*>", "", ref)).strip_code().strip()[:200]
    return d


def claims(wikitext: str) -> List[dict]:
    """Sentences followed by one or more references, numbered in text order."""
    named: Dict[str, str] = {}
    for r in re.findall(REF_TAG, wikitext, re.DOTALL | re.I):
        m = re.search(r"""name\s*=\s*["']?([^"'/>]+)""", r[:r.find(">")])
        if m:
            named.setdefault(m.group(1).strip(), r)
    out: List[dict] = []
    body = wikitext
    chain = re.compile(r"((?:\s*(?:" + REF_TAG + "|" + REF_SELF_CLOSING + r"|\{\{\s*sfn[^}]*\}\}))+)", re.DOTALL | re.I)
    pos = 0
    for m in chain.finditer(body):
        before = body[pos:m.start()]
        pos = m.end()
        prose = mwp.parse(before).strip_code(normalize=True, collapse=True)
        prose = re.sub(r"\s+", " ", prose).strip()
        if not prose:
            continue
        sentence = _SENT_END.split(prose)[-1].strip()
        if len(sentence) < 15:
            continue
        refs = []
        for r in re.findall(REF_TAG + "|" + REF_SELF_CLOSING + r"|\{\{\s*sfn[^}]*\}\}", m.group(1), re.DOTALL | re.I):
            if r.rstrip().endswith("/>"):
                nm = re.search(r"""name\s*=\s*["']?([^"'/>]+)""", r)
                r = named.get(nm.group(1).strip(), r) if nm else r
            refs.append(_ref_details(r))
        out.append({"n": len(out) + 1, "claim": sentence, "refs": refs})
    return out


def _check_public_url(url: str) -> None:
    """
    Cited URLs come from article text, i.e. from strangers. Only public
    http(s) hosts may be fetched: never file://, localhost or a private
    network address (that would let a crafted reference read local files).
    """
    import ipaddress
    import socket
    import urllib.parse
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError(f"only http(s) URLs can be fetched: {url[:80]}")
    try:
        infos = socket.getaddrinfo(u.hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"cannot resolve {u.hostname}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"refusing to fetch a non-public address: {u.hostname}")


def fetch_text(url: str, max_chars: int = 60000) -> str:
    """Readable text of a public web page (scripts, styles and tags stripped)."""
    _check_public_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
        raw = r.read(3_000_000)
        charset = r.headers.get_content_charset() or "utf-8"
    try:
        page = raw.decode(charset, errors="replace")
    except LookupError:
        page = raw.decode("utf-8", errors="replace")
    page = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer|header)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text[:max_chars]


_WORD = re.compile(r"\w{3,}", re.UNICODE)


def passages(text: str, claim: str, k: int = 3, size: int = 900) -> List[str]:
    """The k windows of `text` sharing the most distinct words (and numbers) with `claim`."""
    keys = {w.lower() for w in _WORD.findall(claim)}
    nums = set(re.findall(r"\d{2,}", claim))
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 40]
    chunks: List[str] = []
    for p in paras:
        while len(p) > size:
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 2 else size
            chunks.append(p[:cut])
            p = p[cut:].strip()
        if p:
            chunks.append(p)
    scored = []
    for c in chunks:
        words = {w.lower() for w in _WORD.findall(c)}
        score = len(keys & words) + 2 * len(nums & set(re.findall(r"\d{2,}", c)))
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for s, c in scored[:k] if s > 0]
