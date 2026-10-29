---
name: daily-batch
description: Translate the next N articles from the worklist in one go — parallel translator agents, each article finished and checked — and produce a review table for the human. Use when the user asks for today's batch, to translate the queue, or to translate several articles at once.
argument-hint: "[n] [to <lang>]"
disable-model-invocation: true
---

# Daily batch

The request is: $ARGUMENTS. The default is 8 articles, into the language the user writes in.

1. `queue_next(target_lang, n=N)` returns the smallest queued articles first. Show the list and wait for one "ok" before you spend tokens on them.
2. For each article, call `translate_start(title, target_lang)`. Calls for different articles are independent, so make them in the same turn.
3. Start `translator` subagents **in parallel**, at most 3 at a time. Each one gets its own job directory, the target language and the style guide path.
   - One article failing never stops the batch. Record the failure and carry on.
4. Call `translate_finish(job)` for every translated job.
5. Mark the finished articles with `queue_mark(titles, "translated", target_lang)`.
6. Report one table, sorted with the most attention needed first:

   | Article | Target title | Size | Blocking | Numbers to check | Lang. warnings | Unmapped links | final.wiki |

7. End with the `publish_prep` output for the first article that has no blocking issues, and offer to prepare the rest.

When the human says an article is published, call `queue_mark(titles, "published", …)`.
- A status never goes backwards, so marking twice is harmless.
- Nothing in this skill publishes anything.
