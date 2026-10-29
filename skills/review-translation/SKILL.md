---
name: review-translation
description: Second-opinion review of a finished translation job — meaning, numbers, omissions, names and the target wiki's style guide — reported as blocking / should fix / nice to have, without editing anything. Use when the user asks to review, check or proofread a translation job.
argument-hint: "<job id>"
---

# Review a translation

Job: $ARGUMENTS. If no job was given, call `jobs_list` and take the newest finished one.

1. Call `job_status(job)` to get the job directory, the target language and the report summary.
2. Call `profile_info(target_lang)` to get the style guide path.
3. Start the `reviewer` subagent. Give it the job directory and the style guide path.
4. Pass on its findings unchanged, in the user's language. Keep its line numbers and quotes.
5. Ask the user which findings to apply.
   - Apply only what they approve, by editing `translated.wiki` (not `final.wiki`).
   - Then run `translate_finish` again, so the fixes and checks are re-applied on top.

The reviewer never edits. A pass that fixed things on its own was removed from the predecessor project because it caused regressions. Findings go to the human first.
