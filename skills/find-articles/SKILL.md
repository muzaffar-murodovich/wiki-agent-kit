---
name: find-articles
description: Find articles that exist on a source wiki but are missing from the target wiki — by category, by the links of a page, or by popularity — screen them against the user's topic policy, and keep a worklist with a reason recorded for every rejection. Use when the user wants to know what to translate next, fill their queue, open a category, or asks why an article was queued, rejected or skipped.
argument-hint: "[category or page] [to <lang>]"
---

# Find missing articles

The request is: $ARGUMENTS

Work **with the user, in this conversation**. They can stop you, overrule a call or ask why at any point. Do not hand this off to a background agent: the reasoning is the product. This was learned in wikipedia-translator, where the finder was moved out of a subagent for exactly that reason.

## Before the first category

1. Establish the language pair. Default: `en` → the language the user writes in.
2. Read the user's topic policy, `$WIKIKIT_HOME/policy.md` (default `~/WikiWork/policy.md`), if it exists.
   - It says what they must not translate, e.g. an employer's rules.
   - If it is missing and the user mentions any restriction, offer to write it down there in their words.
3. Call `queue_status` to see what is already known.

## The loop, per category

1. **List.** `missing_in_category(category, target_lang)` returns the members missing on the target wiki that the queue has not seen yet, smallest first. `trim` = only the lead will be translated.
2. **Screen.** `screen_evidence(titles)` returns each candidate's own topical categories. Pass the whole list in one call.
   - **Read the categories.** The title alone is not enough. A trial run of the original finder queued six people whose categories marked them as militant figures, though their titles looked harmless.
   - Judge against the policy. You are judging evidence, not matching keywords: "Critics of X" is not "X", and "killed by X" is not "member of X".
   - When the user has set `TYPESAFE_API_KEY` and the list is long (30+), you may pre-route with `jev_classify`, using the policy's categories as options. Look yourself at everything with `auto: false`, and at a sample of the rest.
3. **Record every decision before moving on.**
   - `queue_add(titles, target_lang, category=…)` for the accepted ones.
   - `queue_reject(titles, reason, category=…)`, grouping titles that share a reason. The reason is in **English** and specific ("member of a militant organisation per categories"), so that "why was X left out?" can be answered months later with `queue_rejected`.
4. **Report** in a few lines: added, rejected (with reasons) and anything borderline. **Stop and wait** for the user to say go on.
5. **Move on.** When a category is exhausted, use `category_tree` or an accepted article's categories to choose the next one.
   - Prefer `new` categories close to the topic.
   - Use `category_skip` with a reason for a category that should never be searched, e.g. one named after a movement the policy excludes.

## Other ways in

- **Red links of a page:** `missing_linked(page, target_lang)` lists the articles a page links to that the target wiki lacks. It is the natural next worklist after translating that page.
- **Popularity:** `pageviews(titles)` ranks candidates by the source wiki's human traffic. Use it when the user asks "which matter most".

## Rules

- Never translate while running this skill. Never open queue files directly. The tools are the interface.
- Talk to the user in their language. Write reasons in English.
- A wrong acceptance costs one article that a human will catch before it is published. A wrong rejection is invisible. When unsure, show the user the evidence and let them decide.
