import json

import pytest

from forgeai.pipeline import Pipeline, RunOptions
from forgeai.regression import run_regression

ARTIFACTS = ["meta.json", "brief.txt", "events.jsonl", "doc_inventory.json", "requirements.json", "requirements.md", "tools.json",
             "agent_v0.yaml", "agent.yaml", "evalset.json", "judge_selftest.json", "tournament.json", "iterations.json",
             "results_final.json", "report.md", "scorecard.json"]


@pytest.fixture(scope="module")
def hr_run(demos, tmp_path_factory):
    rd = tmp_path_factory.mktemp("runs") / "hr_e2e"
    s = Pipeline((demos / "hr" / "brief.txt").read_text(), demos / "hr" / "docs", rd,
                 RunOptions(non_interactive=True, tournament=True, seed=3)).run()
    return rd, s


def test_e2e_all_artifacts(hr_run):
    rd, s = hr_run
    assert s["status"] == "completed", s
    for name in ARTIFACTS:
        assert (rd / name).exists(), name
    req = json.loads((rd / "requirements.json").read_text())
    assert any("pension" in t for t in req["must_refuse"])  # the guard caught the gap
    tools = json.loads((rd / "tools.json").read_text())
    assert tools["attached"] == [] and "weather" in [t["name"] for t in tools["rejected"]]
    sc = json.loads((rd / "scorecard.json").read_text())
    assert sc["heldout_score"] is not None and sc["dev_score"] is not None and sc["seed"] == 3
    assert "What still fails and why" in (rd / "report.md").read_text(encoding="utf-8")
    events = [json.loads(l)["type"] for l in (rd / "events.jsonl").read_text().splitlines()]
    assert events[-1] == "finished" and "iteration_result" in events and "questions_asked" in events


def test_e2e_budget_stop_still_writes_report(demos, tmp_path):
    rd = tmp_path / "tiny"
    s = Pipeline((demos / "hr" / "brief.txt").read_text(), demos / "hr" / "docs", rd, RunOptions(max_tokens=3000)).run()
    assert s["status"] == "failed" and (rd / "report.md").exists()
    assert "budget" in (rd / "report.md").read_text(encoding="utf-8")


def test_budget_stops_optimizer_but_final_eval_still_reported(demos, tmp_path):
    rd = tmp_path / "mid"
    s = Pipeline((demos / "hr" / "brief.txt").read_text(), demos / "hr" / "docs", rd, RunOptions(max_tokens=30000)).run()
    assert s["status"] == "completed" and s["heldout_score"] is not None
    md = (rd / "report.md").read_text(encoding="utf-8")
    assert "Budget exhausted" in md and "cap 30000" in md
    assert "budget" in json.loads((rd / "iterations.json").read_text())["stop_reason"]


def test_e2e_empty_folder_fails_gracefully(tmp_path):
    (tmp_path / "docs").mkdir()
    s = Pipeline("brief", tmp_path / "docs", tmp_path / "run", RunOptions()).run()
    assert s["status"] == "failed" and s["error"]["stage"] == "ingest"
    assert "no usable documents" in (tmp_path / "run" / "report.md").read_text(encoding="utf-8")


def test_approval_edit_then_approve_and_reject(demos, tmp_path):
    calls = []

    def approval(req):
        calls.append(req)
        if len(calls) == 1:
            d = req.model_dump()
            d["must_answer"] = d["must_answer"] + ["employee stock options"]
            return "edit", d
        return "approve", None

    s = Pipeline((demos / "hr" / "brief.txt").read_text(), demos / "hr" / "docs", tmp_path / "a",
                 RunOptions(approve=True), approval_fn=approval).run()
    assert s["status"] == "completed" and len(calls) == 2
    assert "employee stock options" in json.loads((tmp_path / "a" / "requirements.json").read_text())["must_refuse"]
    r = Pipeline("HR brief: leave", demos / "hr" / "docs", tmp_path / "b", RunOptions(approve=True),
                 approval_fn=lambda req: ("reject", None)).run()
    assert r["status"] == "rejected" and (tmp_path / "b" / "report.md").exists()


def test_regression_mode(hr_run, demos):
    rd, _ = hr_run
    out = run_regression(rd, demos / "hr" / "docs_v2")
    assert sum(out["summary"].values()) == len(json.loads((rd / "evalset.json").read_text())["cases"])
    stale = [c for c in out["cases"] if c["status"] == "stale_eval"]
    assert stale  # 25 days -> 28 days, study leave removed
    assert (rd / "regression_report.md").exists()
