"""Exact / filtered lookup over the CSV files in the agent's document folder."""
from __future__ import annotations

from ..textutil import content_tokens


def run(args: dict, ctx: dict) -> dict:
    tables: dict[str, list[dict]] = ctx.get("csv", {})
    if not tables:
        raise ValueError("no CSV files available")
    file = args.get("file")
    if file and file not in tables:
        raise ValueError(f"unknown file {file}; available: {list(tables)}")
    limit = max(1, min(int(args.get("limit", 5) or 5), 20))
    column, value = args.get("column"), args.get("value")
    query = str(args.get("query") or value or "").strip()
    out = []
    for name in [file] if file else list(tables):
        rows = tables[name]
        if column and value is not None:
            v = str(value).lower().strip()
            m = [r for r in rows if v in str(r.get(column, "")).lower()]
        else:
            q = query.lower()
            m = [r for r in rows if any(str(c).lower() == q for c in r.values())]
            if not m and query:
                qt = set(content_tokens(query))
                m = [r for r in rows if qt and qt <= set(content_tokens(" ".join(map(str, r.values()))))]
        out.extend({"file": name, **r} for r in m)
    return {"total_matches": len(out), "matches": out[:limit]}


SPEC = {
    "name": "csv_lookup",
    "description": "Look up rows in the CSV tables. Pass {'query': '<id or words>'} or {'column': '<col>', 'value': '<val>'}.",
    "args": {"query": "string (optional)", "column": "string (optional)", "value": "string (optional)",
             "file": "string (optional)", "limit": "int (optional, default 5)"},
    "run": run,
}
