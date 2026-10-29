---
name: new-profile
description: Create a language profile so the kit translates well into a new target wiki — namespaces from the live wiki, standard section headings and date conventions learned from its existing articles, a style guide, and optional localization rules — written to the user's profile directory. Use when the user wants to translate into a language that has no profile yet, or to improve an existing profile.
argument-hint: "<lang code>"
---

# Create a language profile

Language: $ARGUMENTS

A profile is what makes a translation read as if it were written for that wiki and not just translated into its language. The kit works without one, because links, categories and templates are mapped through Wikidata either way. A profile adds the rest. Built-in example: `profile_info("uz")` shows the Uzbek profile, which was proven in daily production. Read its `style.md` to see what a good one looks like.

1. **Ask the facts.** `site_info("<lang>")` gives the real namespace names: Category, Template and File, in the local language.
2. **Learn conventions from the wiki itself.** Use `search_pages` and `fetch_page` on 4–5 good articles of the target wiki, preferably featured or good articles and biographies. Note:
   - **Section headings.** The local equivalents of References, See also, External links, Biography, Early life, Works, Legacy.
   - **The lead sentence.** How the bold name, the dates and the definition are joined, e.g. a dash, a comma or a verb.
   - **Date formats** in prose and in infoboxes.
   - **Names.** How foreign names are transliterated, and whether there is an established convention.
   - **References.** Local citation and reference-list templates, e.g. the local `{{reflist}}`.
3. **Draft three files** under `$WIKIKIT_HOME/profiles/<lang>/`:
   - `profile.json`: `lang`, `name`, `namespaces`, `template_fallbacks` (en name → local name, for the most common templates without a Wikidata link), `unmapped_templates` (`drop` or `keep`), `trim`, and `attribution.edit_summary` in the local language with the placeholders `{source_lang}`, `{title}` and `{revid}`.
   - `style.md`: the conventions you found, each with one wrong/right example taken from a real article.
   - `localization.json`: optional. Literal replacements applied after translation, mostly section headings, e.g. `"== See also ==": "== … =="`.
4. **Ask a native speaker to check it.** Show the user the style guide and ask them to correct it. They know their wiki; your survey of five articles does not.
5. Run `profile_info("<lang>")` to confirm that it loads.

Language hooks in Python (`fixers.py`: `post_process`, `same_name`, `clean_title`, `check_output`, `check_source`) are for later, once real translations show which errors keep coming back. See the Uzbek profile. Do not write regex fixes on speculation.
