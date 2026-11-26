import json
import time

import pytest
from fastapi.testclient import TestClient

from server.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _sse_events(client, run_id, timeout=120):
    evs = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert r.status_code == 200 and "text/event-stream" in r.headers["content-type"]
        for line in r.iter_lines():
            if line.startswith("data:"):
                evs.append(json.loads(line[5:].strip()))
                if evs[-1]["type"] == "finished":
                    break
    return evs


def _wait_waiting(client, run_id, what, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if client.get(f"/api/runs/{run_id}").json()["waiting"] == what:
            return
        time.sleep(0.1)
    raise AssertionError(f"run never waited for {what}")


def test_full_run_flow_with_sse(client, demos):
    files = [("files", (p.name, p.read_bytes())) for p in (demos / "spares" / "docs").iterdir()]
    brief = (demos / "spares" / "brief.txt").read_text()
    r = client.post("/api/runs", data={"brief": brief, "non_interactive": "false", "tournament": "true"}, files=files)
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    _wait_waiting(client, run_id, "answers")
    assert client.post(f"/api/runs/{run_id}/answers", json={"auto": True}).json() == {"ok": True}
    evs = _sse_events(client, run_id)
    types = [e["type"] for e in evs]
    for t in ("stage_started", "stage_done", "questions_asked", "flags", "iteration_result", "finished"):
        assert t in types, t
    assert evs[-1]["status"] == "completed"

    runs = client.get("/api/runs").json()
    me = next(x for x in runs if x["run_id"] == run_id)
    assert me["heldout_score"] is not None and me["stop_reason"]
    names = [a["name"] for a in client.get(f"/api/runs/{run_id}/artifacts").json()]
    assert "agent.yaml" in names and "report.md" in names
    tools = client.get(f"/api/runs/{run_id}/artifacts/tools.json").json()
    assert sorted(t["name"] for t in tools["attached"]) == ["calculator", "csv_lookup"]
    assert client.get(f"/api/runs/{run_id}/artifacts/../../etc/passwd").status_code in (404, 400)
    z = client.get(f"/api/runs/{run_id}/zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"

    c = client.post("/api/chat", json={"run_id": run_id, "message": "What is the minimum order value for Nordic Marine Supply?"}).json()
    assert set(c) >= {"answer", "sources", "confidence", "refused", "tools_used"}
    off = client.post("/api/chat", json={"run_id": run_id, "message": "Who painted the Sistine Chapel ceiling?"}).json()
    assert off["refused"] is True

    # replay of a finished run's events
    assert _sse_events(client, run_id)[-1]["type"] == "finished"


def test_approval_flow_via_api(client, demos):
    r = client.post("/api/runs", data={"demo": "hr", "approve": "true"})
    run_id = r.json()["run_id"]
    _wait_waiting(client, run_id, "approval")
    assert client.post(f"/api/runs/{run_id}/approval", json={"action": "bogus"}).status_code == 400
    client.post(f"/api/runs/{run_id}/approval", json={"action": "reject"})
    evs = _sse_events(client, run_id)
    assert "approval_requested" in [e["type"] for e in evs] and evs[-1]["status"] == "rejected"


def test_regress_endpoint(client):
    run_id = client.post("/api/runs", data={"demo": "hr"}).json()["run_id"]
    _sse_events(client, run_id)
    r = client.post(f"/api/runs/{run_id}/regress", data={"demo_v2": "true"})
    assert r.status_code == 200 and r.json()["summary"]["stale_eval"] >= 1


def test_clean_json_errors(client):
    assert client.post("/api/runs", data={"brief": "x"}).json()["error"].startswith("upload at least one")
    assert client.post("/api/runs", data={"brief": ""}, files=[("files", ("a.txt", b"hello"))]).status_code == 400
    r = client.get("/api/runs/does_not_exist/artifacts")
    assert r.status_code == 404 and "error" in r.json()
    assert client.post("/api/chat", json={"run_id": "nope", "message": "hi"}).status_code == 404
    assert client.post("/api/runs/nope/answers", json={"auto": True}).status_code == 409
