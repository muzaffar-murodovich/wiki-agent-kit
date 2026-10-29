---
name: wikidata-labels
description: Fill missing Wikidata labels and descriptions in one language for a set of items — the items linked from an article, a translation job, or a list of QIDs — as a linted QuickStatements batch the human runs. Use when the user wants Wikidata labels/descriptions in their language, or after translating an article whose links point to items without labels.
argument-hint: "<job id | article title | Q-ids> [lang]"
---

# Wikidata labels and descriptions

Request: $ARGUMENTS. Default language: the one the user writes in.

Labels in small languages are the cheapest high-impact Wikidata work there is. Every wiki, Wikipedia search box, infobox and AI assistant that reads Wikidata shows them.

1. **Collect the items.**
   - **A job:** `job_status`, then read its `state.json` and take every `qid` under `lookup.pages`.
   - **An article:** `fetch_page`, then `page_info` on its links.
   - **QIDs:** use them as given.
2. **Find the gaps.** `wd_missing_terms(qids, lang)` returns the items lacking a label or description.
3. **Draft.** Give batches of about 40 items to `labeler` subagents running on Haiku, which is cheap, 2–3 in parallel. Each returns QuickStatements lines and an UNSURE list.
4. **Lint.** Run `wd_check_quickstatements(batch)` on the merged batch.
   - Drop any line it flags, unless the fix is obvious.
   - A missing-source warning does not apply to labels and descriptions; ignore it here.
5. **Hand over.**
   - The batch, in a code block, plus a file under `$WIKIKIT_HOME/quickstatements/`.
   - The UNSURE items, for the human to decide.
   - How to run it: https://quickstatements.toolforge.org → New batch → paste → Run. **The human runs it with their own account. You don't.**

Never overwrite an existing label or description. Only fill what is missing.
