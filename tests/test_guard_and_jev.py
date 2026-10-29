"""The PreToolUse guard, Jev request shapes, QuickStatements lint, citation claims."""

import importlib.util
import io
import json
from pathlib import Path

import pytest

from wikikit import cite, jev, wikidata

_spec = importlib.util.spec_from_file_location("guard", Path(__file__).parents[1] / "hooks" / "guard.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def blocked(tool, inp):
    try:
        guard.check(tool, inp)
    except SystemExit as e:
        return e.code == 2
    return False


@pytest.mark.parametrize("cmd", [
    "curl -X POST https://uz.wikipedia.org/w/api.php -d action=edit",
    "curl 'https://www.wikidata.org/w/api.php?action=wbeditentity&id=Q1'",
    "curl 'https://en.wikipedia.org/w/api.php?action=query&meta=tokens'",
    "python -c \"import pywikibot; p=pywikibot.Page(s,'X'); p.save('x')\"",
    "Invoke-WebRequest https://uz.wikipedia.org/w/api.php -Method Post -Body $b",
    "curl -d@body.txt https://uz.wikipedia.org/w/api.php",
    "wget --post-file=b.txt https://uz.wikipedia.org/w/api.php",
    "iwr https://uz.wikipedia.org/w/api.php -Method Post -Body $b",
    "python -c \"import requests; requests.Session().post('https://uz.wikipedia.org/w/api.php', data=d)\"",
    "curl --json '{}' https://www.wikidata.org/w/api.php",
])
def test_guard_blocks_writes(cmd):
    assert blocked("Bash", {"command": cmd})


@pytest.mark.parametrize("cmd", [
    "curl 'https://en.wikipedia.org/w/api.php?action=query&titles=X'",
    "uv run pytest",
    "curl -X POST https://api.typesafe.ai/v1/systemone -d '{}'",   # not a wiki
    "curl -s 'https://uz.wikipedia.org/w/api.php?action=query&list=search&srsearch=x' | cut -d '\"' -f4",
    "curl -s https://en.wikipedia.org/wiki/X | grep -F 'infobox'",
    "curl -G https://en.wikipedia.org/w/api.php --data-urlencode 'titles=A B' -d action=query",
])
def test_guard_allows_reads(cmd):
    assert not blocked("Bash", {"command": cmd})


def test_guard_browser_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "STATE", tmp_path / "tabs.json")
    nav = "mcp__claude-in-chrome__navigate"
    assert blocked(nav, {"url": "https://uz.wikipedia.org/w/index.php?title=X&action=edit", "tabId": 1})
    assert blocked(nav, {"url": "https://uz.wikipedia.org/w/index.php?title=X&veaction=editsource", "tabId": 1})
    assert blocked(nav, {"url": "https://uz.m.wikipedia.org/wiki/X#/editor/0", "tabId": 1})
    assert blocked("mcp__claude-in-chrome__browser_batch", {"actions": [{"navigate": "https://uz.wikipedia.org/wiki/X"}]})
    assert blocked("mcp__claude-in-chrome__computer", {"action": "left_click", "tabId": 99})   # unseen tab
    assert not blocked(nav, {"url": "https://uz.wikipedia.org/wiki/X", "tabId": 1})
    assert blocked("mcp__claude-in-chrome__computer", {"action": "left_click", "tabId": 1})
    assert not blocked(nav, {"url": "https://example.com", "tabId": 2})
    assert not blocked("mcp__claude-in-chrome__computer", {"action": "left_click", "tabId": 2})


def test_guard_main_reads_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(
        {"tool_name": "WebFetch", "tool_input": {"url": "https://uz.wikipedia.org/w/api.php?action=edit"}}).encode())))
    with pytest.raises(SystemExit) as e:
        guard.main()
    assert e.value.code == 2


# ------------------------------------------------------------------ jev

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_jev_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert not jev.available()
    with pytest.raises(jev.JevUnavailable):
        jev.cite_check("c", ["p"])


def test_jev_cite_check_request_and_verdict(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    sent = {}

    def fake_urlopen(req, timeout=None, context=None):
        sent["url"] = req.full_url
        sent["auth"] = req.headers["Authorization"]
        sent["body"] = json.loads(req.data)
        return _Resp(json.dumps({"model": "jev-1.13.0", "answers": {
            "p0": {"type": "choice", "choice": "says_nothing", "probabilities": {"supports": 0.1, "contradicts": 0.0, "says_nothing": 0.9}, "confidence": 0.85},
            "p1": {"type": "choice", "choice": "supports", "probabilities": {"supports": 0.95, "contradicts": 0.0, "says_nothing": 0.05}, "confidence": 0.9},
        }, "usage": {"input_tokens": 10, "output_tokens": 2}}).encode())

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    res = jev.cite_check("He was born in 1043.", ["irrelevant", "born 1043"])
    assert sent["url"] == jev.ENDPOINT and sent["auth"] == "Bearer k"
    q = sent["body"]["questions"]["p1"]
    assert q["type"] == "choice" and set(q["criteria"]) == {"supports", "contradicts", "says_nothing"}
    assert sent["body"]["state"] == {"claim": "He was born in 1043."}
    assert res["verdict"] == "verified" and res["auto"] is True


# ------------------------------------------------------------------ quickstatements

def test_quickstatements_lint(monkeypatch):
    monkeypatch.setattr(wikidata, "_get_entities", lambda ids, props, langs="": {
        "Q1": {"claims": {"P106": [{"mainsnak": {"datavalue": {"value": {"id": "Q2"}}}}]}},
        "Q2": {}, "Q3": {}})
    monkeypatch.setattr(wikidata, "properties", lambda pids, lang="en": {
        "P106": {"label": "occupation", "datatype": "wikibase-item", "exists": True},
        "P569": {"label": "date of birth", "datatype": "time", "exists": True},
        "P1": {"label": None, "datatype": None, "exists": False}})
    batch = "\n".join([
        "Q1\tP106\tQ2\tS143\tQ328",            # duplicate
        "Q1\tP569\t1043",                      # bad time, no source
        "Q1\tP1\tQ3\tS143\tQ328",              # unknown property
        "Q1\tLuz\tIbn Sino",                   # unquoted label
        "Q1\tDuz\t\"fors olimi\"",             # fine
    ])
    res = wikidata.check_quickstatements(batch)
    text = " ".join(res["problems"])
    assert "duplicate" in text and "time must look like" in text
    assert "P1 does not exist" in text and "Luz value must be quoted" in text
    assert not any(p.startswith("line 5") for p in res["problems"])


# ------------------------------------------------------------------ citations

def test_claims_extracts_sentences_with_their_sources():
    wt = ("Intro sentence without a ref. Avicenna was born in Afshana in 980."
          "<ref>{{cite web |url=https://ex.org/a |title=Life}}</ref> "
          "He died in 1037.<ref name=\"d\">{{cite book |title=Death |page=5}}</ref> "
          "Again.<ref name=\"d\"/>")
    items = cite.claims(wt)
    assert items[0]["claim"].startswith("Avicenna was born")
    assert items[0]["refs"][0]["url"] == "https://ex.org/a"
    assert items[1]["refs"][0]["title"] == "Death"


def test_passages_rank_by_overlap():
    text = "Cats are nice animals.\n\nAvicenna was born in Afshana near Bukhara in 980 CE.\n\nOther things entirely unrelated here."
    assert "Afshana" in cite.passages(text, "Avicenna was born in Afshana in 980.", k=1)[0]


def test_guard_reads_utf8_stdin_even_with_cp1252_console(monkeypatch):
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo Ё; curl -X POST https://uz.wikipedia.org/w/api.php"}}
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")), encoding="cp1252"))
    with pytest.raises(SystemExit) as e:
        guard.main()
    assert e.value.code == 2


def test_quickstatements_valid_v1_forms(monkeypatch):
    monkeypatch.setattr(wikidata, "_get_entities", lambda ids, props, langs="": {i: {"claims": {}} for i in ids})
    monkeypatch.setattr(wikidata, "properties", lambda pids, lang="en": {
        "P106": {"label": "occupation", "datatype": "wikibase-item", "exists": True}})
    batch = "CREATE\nLAST\tLen\t\"X\"\nLAST\tP106\tsomevalue\tS143\tQ328\n-Q1\tP106\tQ2\nP106\tLuz\t\"kasbi\""
    assert wikidata.check_quickstatements(batch)["problems"] == []
