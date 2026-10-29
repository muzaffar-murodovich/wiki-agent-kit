# Wiki Agent Kit

**For Wikipedia, Wikidata and Commons editors. No programming needed.**

You name an article and a language. The kit fetches the article, has Claude translate it, and turns every link, category and template into the right page **on your wiki** through Wikidata. It keeps every reference exactly as the source has it. Then it tells you what to check: numbers that changed, names spelled two ways, anything it could not map. **You** read it, fix it, and publish it. The kit cannot: it has no login and no editing code. It also writes the edit summary that credits the source article (as the licence requires) and says the text was machine-assisted and human-reviewed.

It also finds the articles your wiki is missing, checks whether cited sources really say what the article claims, drafts Wikidata labels in your language, and helps you bring templates over from other wikis.

> **The agent drafts. A human publishes.**

## What it does

| Skill (slash command) | What you get |
|---|---|
| `/wikikit:translate-article` | An article translated from any wiki to any other, with every link, category and template mapped through **Wikidata** to the target wiki's real pages. References are passed through byte-for-byte, so the model never sees a citation and cannot alter or invent one. Then: a checked draft, a review checklist, and a CC BY-SA attribution edit summary. |
| `/wikikit:find-articles` | Articles your wiki lacks: by category, by the red links of a page, or by popularity. Each is screened against *your* topic policy, and every rejection keeps its reason. |
| `/wikikit:daily-batch` | The next N articles translated by parallel subagents. The result is one review table. |
| `/wikikit:review-translation` | A bilingual second read. It reports problems by severity and never edits. |
| `/wikikit:verify-citations` | For each cited sentence, the source page is fetched, the relevant passage found, and the claim judged supported / contradicted / not found. |
| `/wikikit:wikidata-labels` | Missing labels and descriptions in your language, drafted as a linted QuickStatements batch. |
| `/wikikit:wikidata-from-article` | The statements an item lacks, each with a source, plus infobox-vs-Wikidata conflicts. |
| `/wikikit:port-template` | Bring an infobox or Lua module to your wiki. You get a dependency map, a check of what already exists locally, and drafts in creation order. |
| `/wikikit:new-profile` | A language profile for your wiki: namespaces, headings, lead-sentence and date conventions learned from your wiki's own articles. |

There are also **38 MCP tools** for direct use, and **4 subagents**:
- `translator` (Sonnet)
- `reviewer` (Sonnet, read-only)
- `cite-checker` (Sonnet)
- `labeler` (Haiku)

## How translation works

```
translate_start                     translator agent              translate_finish
───────────────                     ────────────────              ────────────────
fetch revision ──► trim if long     reads prepared.wiki           Q-ids  → target-wiki titles
                   │                + style guide                 LNK    → names.json
[[Ibn Sina|Avicenna]] → [[Q8011|Avicenna]]   translates prose      ⟦CAT⟧  → local categories
[[Unknown|x]]          → [[LNK1|x]]          keeps placeholders    TPL:Q  → local templates
[[Category:…]]         → ⟦CAT:Q…|…⟧          names unmapped links  REF_…  → original citations
{{Infobox …}}          → {{TPL:Q…}}          (translated.wiki,     profile fixes + localization
<ref>…</ref>           → <ref>REF_1a2b…</ref> names.json)          checks → report.json
```

Each check answers a question a reviewer would otherwise have to dig for:
- **A URL in the translation that isn't in the source.** That is the signature of an invented citation, and it is a blocking error.
- **A number that changed.**
- **A named reference left undefined.** On the wiki it shows up as a "Cite error".
- **Unbalanced markup.**
- **A leftover placeholder.**
- **Your language profile's own checks.**

All state lives in a job folder (`~/WikiWork/jobs/<title>.<src>-<tgt>/`). The steps can therefore run in separate sessions, and article text never passes through the conversation.

## Languages

The kit works **between any two languages**, because Wikidata does the mapping. A **language profile** makes the output native to the target wiki. It lives in `wikikit/profiles/<lang>/` or in your own `~/WikiWork/profiles/<lang>/`, and holds:
- `profile.json`: namespaces, template fallbacks, trim size, attribution wording
- `style.md`: the translator's style guide, with wrong/right examples
- `localization.json`: literal replacements, e.g. section headings
- `fixers.py`, optional: language hooks for deterministic fixes, the link-label comparator and output checks

The **Uzbek profile** (`uz`) comes from [wikipedia-translator](https://github.com/muzaffar-murodovich/wikipedia-translator), which produced translations that were published on uz.wikipedia daily. It covers:
- 252 localization rules
- date and Hijri-year fixes
- Arabic-name transliteration
- a consonant-skeleton comparator that tells `[[Lohur|Lahor]]` (same name, collapse it) from `[[Somalilar|somalilik]]` (grammar, keep it)
- lead-sentence checks

Use `/wikikit:new-profile <lang>` to start a profile for your language.

## Install

You need [Claude Code](https://claude.com/claude-code) and [uv](https://docs.astral.sh/uv/getting-started/installation/). On Windows, uv installs with one PowerShell line:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Claude Code is Anthropic's assistant for the terminal and desktop. It needs a Claude subscription. The uv line above downloads uv's official installer from astral.sh and runs it; that is uv's documented install method.

Then, inside Claude Code:

```
/plugin marketplace add muzaffar-murodovich/wiki-agent-kit
/plugin install wikikit@wiki-agent-kit
```

Claude Code then asks for the plugin's settings. Set your **contact**: an email or a wiki user page. Wikimedia's User-Agent policy requires it. Optionally also set:
- a work directory
- a **TypeSafe API key**, to enable Jev (below)

The first start takes a minute while uv installs the Python dependencies.

To develop:

```bash
uv sync --extra dev
uv run pytest
claude --plugin-dir .
```

## Jev (optional)

[Jev](https://docs.typesafe.ai) by TypeSafe AI is a "System One" decision model, not a text generator. It answers typed questions (pick one option / yes-no / score) with **calibrated confidence** in under a second, at a tiny fraction of an LLM's cost. That fits the bulk, bounded decisions of wiki work. With `TYPESAFE_API_KEY` set:

- **Citation checks** run through `jev_cite_check`. Each claim–passage pair becomes one Choice question: supports / contradicts / says nothing. TypeSafe publishes this pattern as one of its own cookbooks. Confident verdicts are accepted, and only uncertain ones go to Claude or the human.
- **Screening long candidate lists** runs through `jev_classify`, with options taken from your topic policy. Low-confidence items go to you.

Without a key, Claude does both itself. The Jev client follows the published API reference and is unit-tested. It has not yet been run against the live service.

## What counts as "human review"

Most wikis accept machine-assisted translation **only** when someone who reads both languages well checks it. English Wikipedia's WP:LLMT and the German, Russian and Azerbaijani rules all say this. In practice that means:

- You read the **whole** translation against the source, not only the parts the report flags.
- You check every number and date listed in the report against the source.
- You confirm that names of people and places are spelled the way your wiki spells them.
- You preview the page and look for red template names and "Cite error" messages.
- You can vouch for every sentence. If you can't, cut it or leave the article as a shorter stub.

If your wiki forbids machine translation, this kit is not for that wiki, and it says so.

## Your data

- Article text is sent to **Claude** (Anthropic) to be translated, like anything else you type into Claude Code. Your Claude Code plan's data settings apply.
- If you set a TypeSafe key, short passages and claims go to TypeSafe for citation checks.
- Nothing else leaves your computer except **read** requests to Wikimedia APIs.
- Jobs, worklists and profiles are ordinary files in your work folder (`WikiWork` in your home folder). Delete them when you like.

## Telling your community

A short, honest note on your village pump before you publish many translations prevents most of the hostility AI tools meet. A template is in [docs/COMMUNITY.md](docs/COMMUNITY.md).

## Safety, in layers

1. **No credentials, no write code.** The kit cannot log in.
2. **`wikikit/api.py` refuses write actions**: `edit`, `wbeditentity`, `upload`, token requests, and so on. Every request is a GET.
3. **`hooks/guard.py`** (PreToolUse) blocks:
   - write actions sent to Wikimedia sites through Bash, PowerShell or WebFetch
   - pywikibot/mwclient saves
   - edit forms opened in the automated browser
   - clicking or typing in an automated-browser tab that is on a Wikimedia site. Your browser is logged in as you.
4. **Identified, polite traffic.** The User-Agent carries your contact, titles are batched 50 per request, and `maxlag` and `Retry-After` are honoured.
5. **Disclosure and attribution.** `publish_prep` writes an edit summary that credits the exact source revision (CC BY-SA) and states that the text was machine-assisted and human-reviewed.

## Why this matters now

- **English Wikipedia** adopted a guideline in March 2026 that forbids LLM-generated article text, with two exceptions: copyediting your own writing, and **translation reviewed by a human**. Translation is exactly what this kit does.
- **The Wikimedia Foundation's AI strategy** (2025) puts helping editors, translation and under-represented languages first.
- **On 2026-10-05** the Foundation reported unauthorised agent activity on its projects. This kit is the counter-example: it is read-only, identified and rate-limited, and a human publishes.

## Licence

MIT. Content you produce with it is yours to license as the target wiki requires (CC BY-SA 4.0 for Wikipedia, CC0 for Wikidata).
