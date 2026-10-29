---
name: translate-article
description: Translate a Wikipedia (or other wiki) article into another language's wiki with links, categories, templates and references mapped through Wikidata, then hand the human a checked draft and an attribution edit summary. Use when the user asks to translate an article, create an article from another language version, or gives an article title/URL plus a target language.
argument-hint: "<title or URL> [to <lang>] [from <lang>] [full|trim]"
---

# Translate an article

The request is: $ARGUMENTS

You coordinate. Code does the exact work, the `translator` subagent translates, and the human reviews and publishes. **You never publish, and no tool here can.**

## 1. Work out the job

- **Source.** A title, a URL or `lang:Title`. Default source language: `en`.
- **Target language.** Use the one the user names. If they don't, use the language they are talking to you in. Ask only if you still cannot tell.
- **Mode.** `auto` unless the user says `full` or `trim`.
  - `auto` trims long articles to lead + references + categories, above the target profile's threshold.
  - Mention the trim to the user. A trimmed article is a stub to expand later, not a lesser translation.

## 2. Start

Call `translate_start(page, target_lang, source_lang, mode)`. Tell the user, in one or two lines:
- the title and revision
- whether it was trimmed and what was cut
- how many links/categories/templates were mapped
- how many links have no target-wiki article
- any `source_warnings`. These are defects already present in the source, so the human should know about them.

If `counts.failed_lookups` is not empty, the Wikimedia API failed for those titles. Say so: those links stay unmapped. Offer to run it again later.

## 3. Translate

Start **one** `translator` subagent. Give it:
- the job directory (`dir`)
- the target language code
- the `style_guide` path (or "none")

It writes `translated.wiki` and `names.json` and reports its placeholder counts. If the counts don't match, ask it once to fix the mismatch.

Do not translate the article yourself in this conversation. That would fill your context with 30 KB of wikitext.

## 4. Finish

Call `translate_finish(job)`. Read the report and tell the user what needs their eyes. Lead with what matters most:

1. `checks.blocking`
   - a URL not in the source = a possibly invented citation
   - undefined named refs
   - unbalanced markup
   - leftover placeholders
2. `checks.numbers`: numbers that differ between source and translation. Each one must be checked.
3. `checks.language`: the target profile's own warnings, e.g. a lead sentence missing the dash.
4. `label_mismatches` and `links.left_in_source_language`.
5. `templates.kept_without_target`. These templates carry text but have no counterpart on the target wiki. They were kept under their source name, so they will show as red in preview. Suggest `/wikikit:port-template` for each, or replacing it by hand. `templates.removed` lists decoration-only templates that were dropped; mention them only if asked.

Fix a blocking problem only when the fix is mechanical and certain, such as a placeholder the translator dropped that can be restored from `prepared.wiki`.
- Edit `translated.wiki` and run `translate_finish` again.
- Never "fix" a number or a fact without the source in front of you.

## 5. Hand over

Call `publish_prep(job)`. Give the user:
- the path to `final.wiki`. Offer to show the lead.
- `edit_url`, `edit_summary` and the checklist.
- One sentence saying that they read it, they paste it, they save it.

Offer two optional follow-ups: the `reviewer` agent for a second read, and `/wikikit:verify-citations` for the references.

## Rules

- Respect the target wiki's policy on machine translation. Many wikis require a fluent human reviewer and disclosure in the edit summary, and `publish_prep` writes that disclosure for you. If the user wants to skip review, tell them plainly that this is how AI-translated articles get deleted.
- If the user has a topic policy (see the `find-articles` skill: `$WIKIKIT_HOME/policy.md`), it applies here too.
