"""Tool registry: exactly four tools."""
from __future__ import annotations

from . import calculator, csv_lookup, current_date, weather

REGISTRY: dict[str, dict] = {m.SPEC["name"]: m.SPEC for m in (csv_lookup, calculator, current_date, weather)}


def tool_specs(names: list[str] | None = None) -> list[dict]:
    return [{k: v for k, v in s.items() if k != "run"} for n, s in REGISTRY.items() if names is None or n in names]


def run_tool(name: str, args: dict, ctx: dict) -> dict:
    if name not in REGISTRY:
        return {"ok": False, "error": f"unknown tool {name}"}
    try:
        return {"ok": True, "result": REGISTRY[name]["run"](args or {}, ctx)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
