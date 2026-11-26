"""Keyless weather via open-meteo (geocoding + forecast)."""
from __future__ import annotations

import httpx


def run(args: dict, ctx: dict) -> dict:
    loc = str(args.get("location") or "").strip()
    if not loc:
        raise ValueError("location is required")
    client = ctx.get("http_client") or httpx.Client(timeout=8)
    g = client.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": loc, "count": 1}).json()
    if not g.get("results"):
        raise ValueError(f"location not found: {loc}")
    p = g["results"][0]
    f = client.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": p["latitude"], "longitude": p["longitude"],
        "current": "temperature_2m,wind_speed_10m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "forecast_days": 3,
    }).json()
    return {"location": f"{p.get('name')}, {p.get('country', '')}".strip(", "),
            "current": f.get("current", {}), "daily": f.get("daily", {})}


SPEC = {
    "name": "weather",
    "description": "Current weather and 3-day forecast for a named location (open-meteo).",
    "args": {"location": "string, city or port name"},
    "run": run,
}
