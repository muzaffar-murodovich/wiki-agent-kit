"""
wikikit/api.py - The single, read-only HTTP client for every Wikimedia API.

Two guarantees live here and nowhere else:

1. **Nothing is ever written to a wiki.** Every request is a GET, and any
   `action` that edits, uploads, moves, deletes or logs in is refused before
   a socket is opened. The kit drafts; a human publishes. The PreToolUse hook
   in hooks/ guards the shell and web tools the same way, but this check does
   not depend on the hook being installed.

2. **A failed request is never "not found".** Rate limits (429) and 5xx are
   retried with backoff honouring Retry-After; anything still failing is
   raised. Callers must not cache an exception as an absent page.

TLS is verified against certifi, not the platform store: on Windows the
system store ships a minimal root set, so Python fails with
SSLCertVerificationError where a browser works. SSL_CERT_FILE overrides it
for an intercepting corporate proxy.
"""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

import certifi

__all__ = ["WriteRefused", "api", "site_url", "user_agent", "WRITE_ACTIONS"]

# MediaWiki / Wikibase actions that change something. Refused unconditionally.
WRITE_ACTIONS = frozenset({
    "edit", "create", "move", "delete", "undelete", "protect", "upload",
    "filerevert", "rollback", "revisiondelete", "import", "mergehistory",
    "changecontentmodel", "patrol", "review", "stabilize", "tag", "thank",
    "emailuser", "block", "unblock", "userrights", "watch", "options",
    "login", "clientlogin", "createaccount", "setpagelanguage", "managetags",
    "flow", "discussiontoolsedit", "visualeditoredit", "purge",
    "wbeditentity", "wbcreateclaim", "wbsetclaim", "wbremoveclaims",
    "wbsetclaimvalue", "wbsetreference", "wbremovereferences",
    "wbsetqualifier", "wbremovequalifiers", "wbsetlabel", "wbsetdescription",
    "wbsetaliases", "wbsetsitelink", "wblinktitles", "wbmergeitems",
    "wbcreateredirect", "wbsetlabeldescriptionaliases",
    "wblmergelexemes", "wbladdform", "wbleditformelements", "wblremoveform",
    "wbladdsense", "wbleditsenseelements", "wblremovesense",
    "cxsave", "cxpublish", "contenttranslationsave",
})

DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0
BATCH_SIZE = 50          # titles / ids per query — the MediaWiki limit for anonymous users
BATCH_DELAY = 0.2        # polite pause between batches


# Wikimedia's Robot policy (2026): an unauthenticated client makes one request
# at a time and at most 5 per second. One process-wide throttle enforces it,
# however many tools or threads are asking.
MIN_INTERVAL = 0.2
_throttle_lock = threading.Lock()
_last_request = [0.0]


def _throttle() -> None:
    with _throttle_lock:
        wait = _last_request[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


class WriteRefused(PermissionError):
    """Raised for any request that would change a wiki."""


def setting(name: str) -> str:
    """
    A setting from the plugin option (NAME_OPTION) when it was actually set,
    else from the plain environment variable. An unset plugin option can
    arrive empty or as the literal "${user_config.x}"; neither may hide a
    value the user exported in their shell.
    """
    for key in (f"{name}_OPTION", name):
        v = os.environ.get(key, "").strip()
        if v and "${" not in v:
            return v
    return ""


def user_agent() -> str:
    """
    Wikimedia's User-Agent policy requires a way to contact the operator.

    Set WIKIKIT_CONTACT to an email or a wiki user page. Without it the
    requests still work, but heavy use may be blocked.
    """
    contact = setting("WIKIKIT_CONTACT") or "contact not set"
    return f"wiki-agent-kit/0.1 (https://github.com/muzaffar-murodovich/wiki-agent-kit; {contact})"


def _ssl_context() -> ssl.SSLContext:
    custom = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    cafile = custom if custom and os.path.isfile(custom) else certifi.where()
    try:
        return ssl.create_default_context(cafile=cafile)
    except (OSError, ssl.SSLError):
        return ssl.create_default_context(cafile=certifi.where())


_SSL = _ssl_context()

# Short names people type, mapped to API hosts.
_PROJECT_HOSTS = {
    "wikidata": "www.wikidata.org",
    "commons": "commons.wikimedia.org",
    "meta": "meta.wikimedia.org",
    "mediawiki": "www.mediawiki.org",
    "species": "species.wikimedia.org",
    "wikifunctions": "www.wikifunctions.org",
}
_FAMILIES = ("wikipedia", "wiktionary", "wikisource", "wikiquote",
             "wikibooks", "wikinews", "wikivoyage", "wikiversity")


def site_host(site: str) -> str:
    """
    Turn a site spec into an API host.

    Accepted: "en" (en.wikipedia), "uz.wiktionary", "enwiki", "uzwikisource",
    "wikidata", "commons", or a full host "uz.wikipedia.org".
    """
    s = site.strip().lower()
    if s in _PROJECT_HOSTS:
        return _PROJECT_HOSTS[s]
    if s.endswith(".org"):
        return s
    if "." in s:
        lang, family = s.split(".", 1)
        return f"{lang}.{family}.org"
    for family in _FAMILIES:
        if s.endswith(family) and len(s) > len(family):
            return f"{s[:-len(family)]}.{family}.org"
    if s.endswith("wiki") and len(s) > 4:      # "enwiki" -> en.wikipedia
        return f"{s[:-4]}.wikipedia.org"
    return f"{s}.wikipedia.org"


def site_url(site: str) -> str:
    return f"https://{site_host(site)}/w/api.php"


def _check_read_only(params: Dict[str, Any]) -> None:
    action = str(params.get("action", "")).lower()
    if action in WRITE_ACTIONS:
        raise WriteRefused(
            f"wiki-agent-kit never writes to a wiki (refused action={action}). "
            "Copy the draft and publish it yourself."
        )
    # A token request is the first step of every write; reading never needs one.
    if "tokens" in str(params.get("meta", "")).split("|"):
        raise WriteRefused("wiki-agent-kit does not request edit or login tokens.")


def _retry_delay(attempt: int, error: Exception) -> float:
    retry_after = None
    if isinstance(error, urllib.error.HTTPError) and error.headers:
        try:
            retry_after = float(error.headers.get("Retry-After") or "")
        except ValueError:
            retry_after = None
    backoff = DEFAULT_BASE_DELAY * (2 ** attempt)
    return min(max(retry_after or 0.0, backoff), DEFAULT_MAX_DELAY)


def api(params: Dict[str, Any], site: str = "en", timeout: int = 30,
        max_retries: int = DEFAULT_MAX_RETRIES) -> Dict[str, Any]:
    """
    GET the MediaWiki Action API of `site` and return parsed JSON.

    Raises WriteRefused for a write action, the last network/HTTP error when
    every retry fails, and RuntimeError for an API-level error payload.
    """
    params = dict(params)
    _check_read_only(params)
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    params.setdefault("maxlag", "5")
    url = f"{site_url(site)}?{urllib.parse.urlencode(params)}"

    last: Optional[Exception] = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            err = data.get("error") if isinstance(data, dict) else None
            if err:
                if err.get("code") == "maxlag":
                    last = RuntimeError("maxlag")
                else:
                    raise RuntimeError(f"API error {err.get('code')}: {err.get('info')}")
            else:
                return data
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            last = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                raise  # retrying never fixes a certificate
            last = e
        if attempt < max_retries - 1:
            time.sleep(_retry_delay(attempt, last))
    assert last is not None
    raise last


def rest(path: str, site: str = "en", timeout: int = 30) -> Dict[str, Any]:
    """GET a REST endpoint (e.g. "/w/rest.php/v1/page/Foo"). Read-only by construction."""
    url = f"https://{site_host(site)}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    _throttle()
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
        return json.loads(resp.read().decode("utf-8"))
