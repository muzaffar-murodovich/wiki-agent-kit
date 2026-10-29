---
name: wikidata-from-article
description: Compare an article with its Wikidata item and draft the statements the item is missing (birth/death dates and places, occupation, teachers/students, works) with references to the article's own sources, as a linted QuickStatements batch. Also reports infobox-vs-Wikidata conflicts. Use when the user wants to enrich a Wikidata item from an article, or create an item for an article that has none.
argument-hint: "<article title> [site]"
---

# Enrich Wikidata from an article

Article: $ARGUMENTS. Default site: `en`.

1. Call `fetch_page(title, site, save_to=…)` to get the wikitext and the `qid`.
   - **If there is no item:** run `wd_search` on the title and its main alternative names, and show the user the candidates. Most "missing" items exist under another label. Draft a `CREATE` batch only if the user confirms that none of them match.
2. Call `wd_entity(qid, "en|<user lang>")` to see what the item already says.
3. Call `wd_infobox_check(title, site)` to find years where the article and the item disagree. Report these first. They are errors on one side or the other, and only a human with the sources can say which.
4. Read the infobox and the lead. For each fact the item lacks, find the value as a Wikidata item, using `wd_search` and checking the description. Never guess a QID.
   - Typical properties: P569/P570 (dates), P19/P20 (places), P106 (occupation), P1066/P802 (student of / student), P800 (notable work), P140 (religion), P27 (citizenship), P1412 (languages).
5. Draft QuickStatements V1, one statement per line.
   - **Every line carries a source.** Use `S143` (imported from Wikimedia project) with the wiki's item, e.g. `Q328` for English Wikipedia, plus `S4656` with the permanent URL.
   - Better still, when the article cites a reliable source for that fact, use `S248` with that source's item, if it has one.
   - **Dates** use `+YYYY-MM-DDT00:00:00Z/precision`: 9 = year, 10 = month, 11 = day. A Hijri date is not a Gregorian date. Leave out anything the article gives only in the Hijri calendar, unless it also states the Gregorian equivalent.
6. Lint the batch with `wd_check_quickstatements`, fix it, and lint again.
7. Hand over the batch, what each line asserts in plain words, and the instructions for running it in QuickStatements. The human runs it.

Do not add a statement the article does not support. "Probably" is not a value.
