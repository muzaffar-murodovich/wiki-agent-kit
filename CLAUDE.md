# CLAUDE.md: wiki-agent-kit (developer notes)

This is a Claude Code plugin (`.claude-plugin/`, `skills/`, `agents/`, `hooks/`, `.mcp.json`) on top of a Python package (`wikikit/`) that is served as an MCP server. It grew out of `../wikipedia-translator`. Read that project's CLAUDE.md for the history behind the translation rules.

## Invariants (do not break)

1. **Read-only.**
   - Every Wikimedia request goes through `wikikit/api.py` (`api()` / `rest()`). It refuses `WRITE_ACTIONS` and token requests before any socket opens.
   - Never add a POST to a wiki, a login, or a credential. The only POST in the package is `wikikit/jev.py` to TypeSafe.
2. **One throttle.** `api._throttle()` enforces Wikimedia's Robot policy (≤5 req/s, serial). Any new raw HTTP call to Wikimedia must call it.
3. **A failed request is never "not found".** Lookups record failures in `Lookup.failed` and never cache them as absent.
4. **Article text never travels through tool results.** Tools read and write files in a job directory (`$WIKIKIT_HOME/jobs/<title>.<src>-<tgt>/`) and return paths. `fetch_page` inlines text only up to 6000 characters.
5. **Mechanical work in code, judgment in the model.**
   - Placeholders, reference restore, fixes, localization, label collapse and checks are code.
   - Translation, topic screening and naming are the model's.
   - Never move a deterministic rule into skill prose.
6. **Never silently delete content.**
   - A template with no target counterpart is dropped only when it carries no text (`_carries_content`). Otherwise it is kept and reported.
   - Every removal is listed in the report.
7. **Reviewers report, humans apply.** No agent edits a finished translation on its own.
8. **Prefixes are classified by the source wiki's own siteinfo** (`LinkContext`): its localized namespaces, interwiki map and magic words. Never hard-code English namespace names in new link logic.
9. **Anything fetched from a URL found in article text is untrusted.** `cite.fetch_text` only reads public http(s) hosts.

## Layout

- `wikikit/translate.py`: `start()` (fetch → trim → `Preparer.prepare`) and `finish()` (resolve → restore → profile fixes → localize → collapse labels → `checks.run`); `publish_prep()`.
- `wikikit/lookup.py`: batched title→QID→target sitelink; serialisable to `state.json`.
- `wikikit/profiles/`: per-language data and hooks. `uz/` holds the ported production rules (`rules.py` = the old `regex_patterns.py`, `names.py` = `link_labels.py`, `checks.py` = `source_checks.py`) with their tests. Users' own profiles in `$WIKIKIT_HOME/profiles/` override the built-in ones.
- `wikikit/mcp_server.py`: 38 tools. Each is wrapped so that an exception comes back as `{"ok": false, "error": …}`.
- `hooks/guard.py`: standard library only. It must run on any Python and any OS.

## Settings

`api.setting(NAME)` reads the plugin option `NAME_OPTION` (set in `.mcp.json` from `${user_config.*}`) first, then the plain environment variable. An unset plugin option arrives empty or as a literal `${…}`, and must not mask the shell's value. The settings are:
- `WIKIKIT_HOME`
- `WIKIKIT_CONTACT`
- `TYPESAFE_API_KEY`

## Working on it

```bash
uv sync --extra dev
uv run pytest                      # 261 tests, no network
uv run wikikit tools               # list the MCP tools
uv run wikikit translate "Ibn Jurayj" --to uz   # real network, writes ~/WikiWork/jobs/
claude --plugin-dir .              # try the plugin
claude plugin validate .
```

- Tests monkeypatch `lookup.api`, `translate.fetch_wikitext` and `urlopen`. Never hit the network in tests.
- When the MCP server fails at startup, Claude Code caches the failure for 15 minutes. Editing `.mcp.json` clears it.
- `pyproject.toml` names `README.md` as the readme. Without that file, `uv run` cannot build the package and the server dies before it speaks.
