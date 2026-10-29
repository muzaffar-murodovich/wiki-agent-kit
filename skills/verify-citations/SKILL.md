---
name: verify-citations
description: Check whether the sources cited in an article actually support the sentences that cite them — fetch each cited web page, find the relevant passage, and report supported / contradicted / not found. Works on a translation job, a local wikitext file, or any live article. Use when the user asks to verify, fact-check or audit references.
argument-hint: "<job id | file | article title> [site]"
---

# Verify citations

Target: $ARGUMENTS

1. **Get the wikitext into a file.**
   - **A job:** use its `input.wiki`. The source's claims are what the citations were written for, and the translation keeps the same references.
   - **A live article:** `fetch_page(title, site, save_to=…)`.
   - **A file:** use it as it is.
2. **List the claims.** `cite_claims(path)` returns every sentence followed by a reference, with the reference's URL, title and quote.
3. **Split the work.** Make batches of about 8 claims that have URLs and give each batch to a `cite-checker` subagent, at most 3 in parallel.
   - Claims citing books without URLs are `offline`. List them for the human; don't fetch them.
4. **Merge the results** into one table, worst first:
   - `contradicted`
   - `not found`
   - `unavailable`
   - `supported`
   - `offline`

   Quote the evidence.
5. **Say what it means** for a translation job: a contradicted claim in the source is an error in the source article. The translation should not "fix" it silently, so suggest the user raise it on the source article's talk page.

When `jev_available` is true (see `kit_status`), the cite-checkers call Jev first. Jev returns calibrated confidence: confident verdicts are accepted, and only the uncertain ones reach the human. That is how a 100-reference article can be checked in a few minutes.

Never add, replace or remove a reference yourself. Report only.
