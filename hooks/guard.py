#!/usr/bin/env python3
"""
hooks/guard.py - PreToolUse guard: no tool call may publish to a Wikimedia wiki.

The kit's own MCP tools cannot write (wikikit/api.py refuses write actions
before opening a socket). This hook covers everything else Claude can reach
in the same session:

  * Bash / PowerShell: an HTTP POST, a write `action=`, or a token request
    aimed at a Wikimedia domain; pywikibot / mwclient / wikitools saving.
  * WebFetch: a write `action=` in the URL.
  * Browser automation (Claude in Chrome, the desktop browser pane): the
    browser is logged into the user's wiki account, which makes it the most
    realistic path to an accidental publish. Navigating to an edit or submit
    URL is refused, and clicking, typing, form-filling or running JavaScript
    in a tab last seen on a Wikimedia site is refused too.

It is defence in depth, not the guarantee: the guarantee is that the kit holds
no credentials and has no write code. Set WIKIKIT_GUARD=off to disable.

Standard library only, so it runs under any Python on any OS. Exit code 2
blocks the call and shows stderr to Claude.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

WIKI_HOST = re.compile(
    r"(?:[a-z0-9-]+\.)?(?:wikipedia|wiktionary|wikisource|wikiquote|wikibooks|wikinews|"
    r"wikivoyage|wikiversity|wikidata|wikimedia|mediawiki|wikifunctions)\.org", re.I)
WRITE_ACTION = re.compile(
    r"action=(?:edit|submit|create|move|delete|undelete|protect|upload|rollback|import|"
    r"wbeditentity|wbset\w*|wbcreate\w*|wbremove\w*|wbmerge\w*|wblinktitles|"
    r"login|clientlogin|createaccount|options|visualeditoredit|cxsave|cxpublish)\b", re.I)
# Edit forms: ?action=edit|submit, ?veaction=edit / editsource, the mobile editor #/editor/N
VE_EDIT = re.compile(r"[?&](?:veaction=edit\w*|action=(?:edit|submit))\b|#/editor/", re.I)
# A command segment that runs an HTTP client
HTTP_CLIENT = re.compile(r"(?:^|[\s(`'\"])(?:curl|wget|http|https|xh|Invoke-WebRequest|iwr|Invoke-RestMethod|irm)(?:\.exe)?\b", re.I)
# Flags that make such a client send a body (curl -G/--get turns -d into a query string)
HTTP_WRITE_FLAGS = re.compile(
    r"(?:-X\s*['\"]?(?:POST|PUT|PATCH|DELETE)|--request\s+['\"]?(?:POST|PUT)|(?<!\S)-d|--data\b|--data-\w+|"
    r"(?<!\S)-F|--form\b|--json\b|--post-(?:data|file)\b|-Method\s+['\"]?(?:Post|Put)|-Body\b)", re.I)
CURL_GET = re.compile(r"(?<!\S)(?:-G|--get)\b")
# Library calls that send a body, in a one-liner or a here-doc
CODE_WRITE = re.compile(r"\.(?:post|put|patch)\s*\(|urlopen\([^)]*data\s*=|method\s*=\s*['\"](?:POST|PUT)", re.I)
TOKEN = re.compile(r"meta=tokens|type=(?:csrf|login)", re.I)
BOT_SAVE = re.compile(r"(?:pywikibot|mwclient|wikitools|mwapi)\b[\s\S]*?\.(?:save|put|edit|upload|post)\s*\(", re.I)
BROWSER_INTERACT = re.compile(
    r"(?:claude-in-chrome|Claude_Browser|browser)\w*__(?:computer|form_input|javascript_tool|"
    r"file_upload|upload_image|browser_batch|shortcuts_execute)$", re.I)
BROWSER_NAV = re.compile(r"(?:claude-in-chrome|Claude_Browser|browser)\w*__navigate$", re.I)

STATE = Path(tempfile.gettempdir()) / "wikikit-guard-tabs.json"


def deny(reason: str) -> None:
    sys.stderr.write(
        f"wiki-agent-kit guard: {reason}\n"
        "Publishing is the human's step. Prepare the text and the edit summary "
        "(publish_prep), and let the user open the edit page and save.\n")
    sys.exit(2)


def _tabs() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _remember(tab, url: str) -> None:
    tabs = _tabs()
    tabs[str(tab)] = url
    try:
        STATE.write_text(json.dumps(tabs))
    except OSError:
        pass


def check(tool: str, inp: dict) -> None:
    if tool in ("Bash", "PowerShell"):
        cmd = str(inp.get("command", ""))
        if BOT_SAVE.search(cmd):
            deny("a bot framework call that saves pages")
        if WIKI_HOST.search(cmd) or "api.php" in cmd or "index.php" in cmd:
            if WRITE_ACTION.search(cmd):
                deny("a write action sent to a wiki API")
            if TOKEN.search(cmd):
                deny("an edit/login token request")
            if CODE_WRITE.search(cmd):
                deny("code that sends a request body to a Wikimedia site")
            # Only the HTTP client's own flags count: `cut -d`, `grep -F` are not uploads.
            for seg in re.split(r"\|\||&&|[|;\n]", cmd):
                if HTTP_CLIENT.search(seg) and HTTP_WRITE_FLAGS.search(seg) and not CURL_GET.search(seg):
                    deny("an HTTP request with a body sent to a Wikimedia site")
        return
    if tool == "WebFetch":
        url = str(inp.get("url", ""))
        if WIKI_HOST.search(url) and (WRITE_ACTION.search(url) or TOKEN.search(url)):
            deny("a write action in a wiki URL")
        return
    if BROWSER_NAV.search(tool):
        url = str(inp.get("url", ""))
        if WIKI_HOST.search(url) and VE_EDIT.search(url):
            deny("opening a wiki edit form in the automated browser")
        if "tabId" in inp:
            _remember(inp["tabId"], url)
        return
    if BROWSER_INTERACT.search(tool):
        blob = json.dumps(inp, ensure_ascii=False)
        if WIKI_HOST.search(blob):
            deny("a browser action that involves a Wikimedia page (the browser is logged in as you)")
        tab = inp.get("tabId")
        if tab is None or str(tab) not in _tabs():
            deny("a browser action on a tab the guard has not seen navigate. Navigate the tab "
                 "first, so the guard can tell whether it is on a Wikimedia site")
        if WIKI_HOST.search(_tabs().get(str(tab), "")):
            deny("interacting with a Wikimedia page in the automated browser (it is logged in as you)")


def main() -> None:
    if os.environ.get("WIKIKIT_GUARD", "").lower() == "off":
        return
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")   # never the console code page
    try:
        data = json.loads(raw)
    except Exception:
        if WIKI_HOST.search(raw):
            deny("could not read the tool call, and it mentions a Wikimedia site")
        return
    check(str(data.get("tool_name", "")), data.get("tool_input") or {})


if __name__ == "__main__":
    main()
