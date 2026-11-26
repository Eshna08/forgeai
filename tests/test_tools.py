import httpx
import pytest

from forgeai.tools import REGISTRY, run_tool
from forgeai.tools.calculator import evaluate


def test_registry_has_exactly_four_tools():
    assert set(REGISTRY) == {"csv_lookup", "calculator", "current_date", "weather"}


@pytest.mark.parametrize("expr,val", [("2+3*4", 14), ("4 * 412.50", 1650.0), ("round(10/3, 2)", 3.33), ("1,200 * 0.95", 1140.0), ("-(2**3)", -8)])
def test_calculator_ok(expr, val):
    assert evaluate(expr) == pytest.approx(val)


@pytest.mark.parametrize("expr", ["__import__('os').system('dir')", "open('x')", "[1,2]", "a+1", "(lambda: 1)()",
                                  "2**10000", "().__class__", "'a'*3", "True+1"])
def test_calculator_rejects_unsafe(expr):
    with pytest.raises((ValueError, SyntaxError)):
        evaluate(expr)


def test_run_tool_wraps_errors():
    r = run_tool("calculator", {"expression": "import os"}, {})
    assert r["ok"] is False and "error" in r
    assert run_tool("nope", {}, {})["ok"] is False


def test_csv_lookup_exact_and_column():
    ctx = {"csv": {"c.csv": [{"part_id": "SP-0001", "name": "Fuel injector nozzle", "unit_price": "10.00"},
                             {"part_id": "SP-0002", "name": "Piston ring set", "unit_price": "20.00"}]}}
    r = run_tool("csv_lookup", {"query": "SP-0002"}, ctx)
    assert r["ok"] and r["result"]["matches"][0]["name"] == "Piston ring set"
    r = run_tool("csv_lookup", {"column": "name", "value": "fuel"}, ctx)
    assert r["result"]["total_matches"] == 1
    assert run_tool("csv_lookup", {"query": "x"}, {})["ok"] is False


def test_current_date_fixed():
    r = run_tool("current_date", {}, {"today": "2026-01-15"})
    assert r["result"] == {"date": "2026-01-15", "weekday": "Thursday"}


def test_weather_with_mock_transport():
    def handler(req: httpx.Request):
        if "geocoding" in req.url.host:
            return httpx.Response(200, json={"results": [{"name": "Rotterdam", "country": "NL", "latitude": 51.9, "longitude": 4.5}]})
        return httpx.Response(200, json={"current": {"temperature_2m": 11}, "daily": {}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    r = run_tool("weather", {"location": "Rotterdam"}, {"http_client": client})
    assert r["ok"] and r["result"]["current"]["temperature_2m"] == 11
