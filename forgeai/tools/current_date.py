from __future__ import annotations

import datetime as dt


def run(args: dict, ctx: dict) -> dict:
    today = ctx.get("today") or dt.date.today()
    if isinstance(today, str):
        today = dt.date.fromisoformat(today)
    return {"date": today.isoformat(), "weekday": today.strftime("%A")}


SPEC = {
    "name": "current_date",
    "description": "Return today's date (ISO) and weekday. Use for deadlines / days-remaining questions.",
    "args": {},
    "run": run,
}
