"""
wikikit/cli.py - A thin command line over the same functions the MCP server exposes.

    wikikit translate "Ibn Jurayj" --to uz      start a job (fetch, trim, prepare)
    wikikit finish Ibn_Jurayj.en-uz             resolve, restore, fix, check
    wikikit prep Ibn_Jurayj.en-uz               edit URL + attribution summary
    wikikit jobs                                recent jobs
    wikikit tools                               list every MCP tool
    wikikit call page_info '{"titles": ["Avicenna"], "target_lang": "uz"}'

For tests, debugging, and people who prefer a terminal. Claude uses the MCP
server; both call the same code.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to cp1252
    p = argparse.ArgumentParser(prog="wikikit", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("translate", help="start a translation job")
    t.add_argument("page")
    t.add_argument("--to", required=True, dest="target")
    t.add_argument("--from", default="en", dest="source")
    t.add_argument("--mode", default="auto", choices=["auto", "full", "trim"])
    t.add_argument("--file", help="translate this wikitext file instead of fetching")

    f = sub.add_parser("finish", help="finalize a translated job")
    f.add_argument("job")
    s = sub.add_parser("status", help="one job's stage and report summary")
    s.add_argument("job")
    pr = sub.add_parser("prep", help="publish preparation (does not publish)")
    pr.add_argument("job")
    pr.add_argument("--title")
    sub.add_parser("jobs", help="recent jobs")
    sub.add_parser("tools", help="list MCP tools")
    c = sub.add_parser("call", help="call any MCP tool with JSON arguments")
    c.add_argument("tool")
    c.add_argument("args", nargs="?", default="{}")

    a = p.parse_args(argv)
    from wikikit import translate
    if a.cmd == "translate":
        text = open(a.file, encoding="utf-8").read() if a.file else None
        _print(translate.start(a.page, a.target, a.source, a.mode, text))
    elif a.cmd == "finish":
        _print(translate.finish(a.job))
    elif a.cmd == "status":
        _print(translate.job_status(a.job))
    elif a.cmd == "prep":
        _print(translate.publish_prep(a.job, a.title))
    elif a.cmd == "jobs":
        _print(translate.list_jobs())
    else:
        from wikikit.mcp_server import server
        if a.cmd == "tools":
            for tl in asyncio.run(server.list_tools()):
                print(f"{tl.name:28} {(tl.description or '').splitlines()[0]}")
        else:
            res = asyncio.run(server.call_tool(a.tool, json.loads(a.args)))
            for block in res.content:
                print(getattr(block, "text", block))
    return 0


if __name__ == "__main__":
    sys.exit(main())
