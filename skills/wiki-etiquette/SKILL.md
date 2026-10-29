---
name: wiki-etiquette
description: Background rules for any AI-assisted work on Wikipedia, Wikidata or Commons — what wikis accept from AI tools, attribution, disclosure, bot policy, rate limits. Consult before advising a user on publishing, mass edits, or automating anything on a wiki.
user-invocable: false
---

# Working on wikis with AI: the rules that matter

**Status as of October 2026.** Every wiki sets its own policy. When in doubt, check the target wiki's own policy page and village pump.

## What communities accept, and what they delete

- **English Wikipedia** (guideline adopted March 2026) prohibits using LLMs to generate or rewrite article content. It makes two exceptions:
  - copyediting your own writing;
  - translating from another language's Wikipedia, following WP:LLM-assisted translation.

  Unreviewed LLM text can be speedily deleted under criterion G15.
- **Most other wikis** have similar rules or none yet. Where there is no rule, the community still judges by the same standards: text that is faithful, sourced, reviewed and disclosed.
- **What gets welcomed:** tools that check, map, find and verify, and machine-assisted translation reviewed by a fluent human.
- **What gets resented:** generated prose, unattended agents editing, high-volume scraping, and new "facts" without sources.
- **Recent context.** On 2026-10-05 the Wikimedia Foundation reported agents operating from OpenAI's environment. They edited wikis, tried to misuse tools, and made millions of API requests. Expect editors to be wary of anything that looks autonomous. This kit is the opposite by design: it is read-only, it identifies itself, and a human publishes.

## When the user publishes

- **Attribution (CC BY-SA).** A translation credits its source in the edit summary, with a link to the revision. `publish_prep` writes this.
- **Disclosure.** Say in the edit summary that the text is machine-assisted and human-reviewed.
- **Review.** The publisher must read the text in full and must know both languages well enough to vouch for it.
- **Volume.** Many new articles a day from one account looks like mass creation. Advise the user to talk to their community first, e.g. on the village pump or with admins. On small wikis, a short note listing what they translate and how is usually welcomed.

## Automation

- **Editing by script is a bot.** It needs community approval and a bot flag. This kit has no editing code. If the user asks you to automate saving, explain this instead of writing the code.
- **Reading is fine with limits.**
  - Send a descriptive User-Agent with contact information. Set it in the plugin options.
  - Make requests serially, batch them 50 titles per request, and honour `Retry-After` and `maxlag`.
  - The kit does all of this.
- **Wikidata.** Content is CC0. Labels and descriptions follow per-language conventions. Statements need references, except for a few structural properties. QuickStatements runs under the user's own account, so the user is responsible for each batch.
- **Commons.** Every file has its own licence. Check it with `commons_file_info` before suggesting an image, and never suggest a non-free file.
