"""
wikikit/jev.py - Optional: TypeSafe AI's Jev for fast, calibrated decisions.

Jev (TypeSafe AI, launched 2026-09-15) is not a text generator. It answers
typed questions about a piece of state — pick one option (Choice), yes/no
(Noul), rate on a rubric (Score) — and returns probabilities and a
confidence in 70–500 ms, at a tiny fraction of an LLM's price.

That shape fits the bulk, bounded decisions of wiki work, where an LLM is
overkill and its unstated certainty is the problem:

  cite_check()   does this source passage support / contradict / not address
                 this claim?  (TypeSafe's own "Double-checking citations"
                 cookbook does exactly this)
  classify()     route each of N items to one of a few options — e.g. screen
                 300 candidate articles by their categories — and say how sure

Confidence-gated routing is the point: confident answers are acted on,
uncertain ones go to Claude or the human. Without TYPESAFE_API_KEY every
function raises JevUnavailable and the skills fall back to Claude.

API: POST https://api.typesafe.ai/v1/systemone (docs.typesafe.ai/api).
Not exercised against the live service during development (no key); the
request/response shapes follow the published reference and are unit-tested.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from wikikit.api import _SSL, setting, user_agent

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
def _model() -> str:
    return setting("TYPESAFE_MODEL") or "jev-latest"
AUTO_ACCEPT = 0.8   # confidence at or above which an answer stands without a human

RELATION = {
    "supports": "The passage states the claim or directly implies that it is true",
    "contradicts": "The passage states the opposite of the claim or implies it is false",
    "says_nothing": "The passage does not address what the claim asserts, either way",
}


class JevUnavailable(RuntimeError):
    pass


def _key() -> Optional[str]:
    return setting("TYPESAFE_API_KEY") or None


def available() -> bool:
    return _key() is not None


def evaluate(state, questions: Dict[str, dict], model: Optional[str] = None, timeout: int = 30) -> dict:
    key = _key()
    if not key:
        raise JevUnavailable("TYPESAFE_API_KEY is not set")
    body = json.dumps({"state": state, "model": model or _model(), "questions": questions}, ensure_ascii=False).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise JevUnavailable(f"Jev HTTP {e.code}: {e.read()[:300]!r}") from e
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        # Any failure means "fall back to Claude", never a crash in the skill.
        raise JevUnavailable(f"Jev unreachable: {e}") from e


def cite_check(claim: str, passages: List[str]) -> dict:
    """
    One Choice per passage in a single request (speculative fan-out).

    The verdict is the best-supported relation across passages: any confident
    "supports" verifies; otherwise a confident "contradicts" flags; otherwise
    the claim is unsupported by what was retrieved.
    """
    if not passages:
        return {"verdict": "unsupported", "confidence": None, "auto": False, "reason": "no relevant passage found"}
    questions = {
        f"p{i}": {"type": "choice",
                  "instructions": {"passage": p, "question": "How does `passage` relate to the claim in the state?"},
                  "criteria": RELATION}
        for i, p in enumerate(passages)
    }
    res = evaluate({"claim": claim}, questions)
    answers = res.get("answers", {})
    by_choice = lambda c: [a for a in answers.values() if a.get("choice") == c]
    conf = lambda a: a.get("confidence") or 0
    if by_choice("supports"):
        pick, verdict = max(by_choice("supports"), key=conf), "verified"
    elif by_choice("contradicts"):
        pick, verdict = max(by_choice("contradicts"), key=conf), "contradicted"
    else:
        pick, verdict = max(answers.values(), key=conf, default={}), "unsupported"
    conf = pick.get("confidence")
    return {"verdict": verdict, "confidence": conf, "auto": bool(conf is not None and conf >= AUTO_ACCEPT),
            "per_passage": {k: {"choice": a.get("choice"), "confidence": a.get("confidence")} for k, a in answers.items()},
            "usage": res.get("usage")}


def classify(items: Dict[str, object], question: str, options: Dict[str, str]) -> Dict[str, dict]:
    """
    Route each item to one option. `items` maps an id to its state (text or
    object, e.g. {"title": ..., "categories": [...]}); one request per item.
    """
    out: Dict[str, dict] = {}
    for item_id, state in items.items():
        res = evaluate(state, {"route": {"type": "choice", "instructions": question, "criteria": options}})
        a = res.get("answers", {}).get("route", {})
        conf = a.get("confidence")
        out[item_id] = {"choice": a.get("choice"), "confidence": conf,
                        "probabilities": a.get("probabilities"),
                        "auto": bool(conf is not None and conf >= AUTO_ACCEPT)}
    return out
