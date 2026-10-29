---
name: port-template
description: Bring a template or Lua module from one wiki to another — map its dependencies, find which already exist locally under other names, translate parameter labels and documentation, and write ready-to-create page drafts in creation order. Use when the user wants to copy, port, import or localize a template, infobox or module to their wiki.
argument-hint: "<Template:Name | Module:Name> [to <lang>] [from <lang>]"
---

# Port a template

Request: $ARGUMENTS

1. Call `template_port_plan(template, target_lang, source_lang)`.
   - **If the template already exists on the target wiki** (`exists_on_target`), say so and stop, unless the user wants to *update* it. In that case, compare the two versions with `fetch_page` on both wikis.
   - Report how many dependencies it has, how many are missing, and the creation order. Modules come first, then the smallest templates, and the requested template last.
2. For each missing page, in creation order:
   - Get the source with `fetch_page(..., save_to=$WIKIKIT_HOME/ports/<template>/<n>-<name>.source)`.
   - Write a localized draft next to it, `<n>-<name>.wiki` or `.lua`:
     - **Keep the code identical.** A Lua module or parser-function logic is copied as-is. Change only what the target wiki needs:
       - names of dependencies that exist there under another name: use the plan's `target` field
       - user-visible strings: labels, error messages, documentation
       - category names, through the target profile or `page_info`
     - **Keep parameter names in the source language.** Add local-language aliases only if the user asks. Articles translated from the source wiki then keep working unchanged.
     - Translate the TemplateData `label` and `description` (from the plan's `templatedata`) into the `/doc` page draft.
   - At the top of each draft, as a comment, put the attribution the source wiki's licence requires. Use the same wording in the edit summary: `Copied from [[:<src>:<Title>]] (revision <revid>)`.
3. Hand over:
   - the list of drafts in creation order, each with its target page name and an `action=edit` URL
   - the edit summary
   - a note to create them in that order and preview the root template on a test page before using it in articles

Never create pages yourself. Lua modules in particular must be checked by someone with template editor rights on the target wiki.
