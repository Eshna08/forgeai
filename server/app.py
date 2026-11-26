"""FastAPI backend: runs (background thread + SSE events), intake answers, approval, artifacts, chat, regression."""
from __future__ import annotations

import asyncio
import io
import json
import shutil
import threading
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import yaml
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from forgeai.config import ROOT, get_settings
from forgeai.ingest import SUPPORTED
from forgeai.pipeline import Pipeline, RunOptions, new_run_id, resolve_path
from forgeai.regression import run_regression
from forgeai.runner import AgentRuntime

WAIT_S = 900  # how long a run waits for intake answers / approval before ForgeAI proceeds on its own
DEMOS = {d: ROOT / "demos" / d for d in ("hr", "spares", "admissions")}

app = FastAPI(title="ForgeAI", version="1.0")


class RunState:
    def __init__(self, run_id: str, run_dir: Path):
        self.run_id, self.run_dir = run_id, run_dir
        self.events: list[dict] = []
        self.done = False
        self.waiting: str | None = None
        self.questions: list[str] = []
        self.answers: list | None = None
        self.answers_evt = threading.Event()
        self.approval: tuple[str, dict | None] | None = None
        self.approval_evt = threading.Event()

    def emit(self, ev: dict) -> None:
        if ev["type"] == "questions_asked":
            self.questions = ev.get("questions", [])
        self.events.append(ev)

    def answer_fn(self, questions: list[str]):
        self.waiting = "answers"
        got = self.answers_evt.wait(WAIT_S)
        self.answers_evt.clear()
        self.waiting = None
        return self.answers if got else None

    def approval_fn(self, req):
        self.waiting = "approval"
        got = self.approval_evt.wait(WAIT_S)
        self.approval_evt.clear()
        self.waiting = None
        decision = self.approval if got else ("approve", None)
        self.approval = None
        return decision


RUNS: dict[str, RunState] = {}
AGENTS: dict[str, AgentRuntime] = {}


def runs_dir() -> Path:
    d = get_settings().runs_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_path(run_id: str) -> Path:
    p = (runs_dir() / run_id).resolve()
    if p.parent != runs_dir().resolve() or not p.is_dir():
        raise HTTPException(404, f"run not found: {run_id}")
    return p


def read_meta(p: Path) -> dict:
    try:
        return json.loads((p / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@app.exception_handler(HTTPException)
async def http_err(_: Request, e: HTTPException):
    return JSONResponse({"error": e.detail}, status_code=e.status_code)


@app.exception_handler(Exception)
async def any_err(_: Request, e: Exception):
    return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


# ------------------------------------------------------------------ runs
@app.post("/api/runs")
async def create_run(brief: str = Form(""), files: list[UploadFile] = File(default=[]), approve: bool = Form(False),
                     tournament: bool = Form(False), seed: int = Form(42), non_interactive: bool = Form(True),
                     demo: str = Form("")):
    run_id = new_run_id()
    rd = runs_dir() / run_id
    docs = rd / "docs"
    docs.mkdir(parents=True)
    if demo:
        if demo not in DEMOS:
            raise HTTPException(400, f"unknown demo {demo}; choose from {list(DEMOS)}")
        for f in (DEMOS[demo] / "docs").iterdir():
            shutil.copy2(f, docs / f.name)
        brief = brief or (DEMOS[demo] / "brief.txt").read_text(encoding="utf-8")
    warnings = []
    for f in files:
        name = Path(f.filename or "").name
        if not name:
            continue
        if Path(name).suffix.lower() not in SUPPORTED:
            warnings.append(f"{name}: unsupported type, ignored")
            continue
        (docs / name).write_bytes(await f.read())
    if not brief.strip():
        shutil.rmtree(rd, ignore_errors=True)
        raise HTTPException(400, "brief is required")
    if not any(docs.iterdir()):
        shutil.rmtree(rd, ignore_errors=True)
        raise HTTPException(400, "upload at least one document (txt, md, pdf, docx, csv)")
    st = RunState(run_id, rd)
    RUNS[run_id] = st
    opts = RunOptions(non_interactive=non_interactive, approve=approve, tournament=tournament, seed=seed)
    p = Pipeline(brief, docs, rd, opts, emit=st.emit, answer_fn=st.answer_fn, approval_fn=st.approval_fn)

    def work():
        try:
            p.run()
        finally:
            st.done = True

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": run_id, "warnings": warnings}


@app.get("/api/runs")
def list_runs():
    out = []
    for p in sorted(runs_dir().iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        m = read_meta(p)
        if not m:
            continue
        live = RUNS.get(p.name)
        req = _json(p / "requirements.json") or {}
        tools = (_json(p / "tools.json") or {}).get("attached", [])
        out.append({"run_id": p.name, "brief": m.get("brief", "")[:200], "title": req.get("title"),
                    "tags": [t["name"] for t in tools] + [x for x in req.get("must_answer", [])[:2]], "status": "running" if live and not live.done else m.get("status", "unknown"),
                    "heldout_score": m.get("heldout_score"), "dev_score": m.get("dev_score"), "stop_reason": m.get("stop_reason"),
                    "provider": m.get("provider"), "started_at": m.get("started_at"), "has_agent": (p / "agent.yaml").exists()})
    return out


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    p = run_path(run_id)
    st = RUNS.get(run_id)
    return {"run_id": run_id, "meta": read_meta(p), "done": st.done if st else True,
            "waiting": st.waiting if st else None, "questions": st.questions if st else []}


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, since: int = 0):
    p = run_path(run_id)
    st = RUNS.get(run_id)

    async def gen():
        i = since
        if st is None:  # finished run from a previous server session: replay the log
            for line in (p / "events.jsonl").read_text(encoding="utf-8").splitlines()[since:]:
                ev = json.loads(line)
                yield {"event": ev["type"], "data": line}
            return
        while True:
            while i < len(st.events):
                ev = st.events[i]
                i += 1
                yield {"event": ev["type"], "data": json.dumps(ev, default=str)}
            if st.done and i >= len(st.events):
                return
            await asyncio.sleep(0.2)

    return EventSourceResponse(gen())


class Answers(BaseModel):
    answers: list[str | None] = []
    auto: bool = False  # "let ForgeAI answer"


@app.post("/api/runs/{run_id}/answers")
def post_answers(run_id: str, body: Answers):
    st = RUNS.get(run_id)
    if not st or st.done:
        raise HTTPException(409, "run is not waiting for answers")
    st.answers = None if body.auto else body.answers
    st.answers_evt.set()
    return {"ok": True}


class Approval(BaseModel):
    action: str  # approve | edit | reject
    requirements: dict | None = None


@app.post("/api/runs/{run_id}/approval")
def post_approval(run_id: str, body: Approval):
    st = RUNS.get(run_id)
    if not st or st.done:
        raise HTTPException(409, "run is not waiting for approval")
    if body.action not in ("approve", "edit", "reject"):
        raise HTTPException(400, "action must be approve, edit or reject")
    if body.action == "edit" and not body.requirements:
        raise HTTPException(400, "edit needs the edited requirements object")
    st.approval = (body.action, body.requirements)
    st.approval_evt.set()
    return {"ok": True}


# ------------------------------------------------------------------ artifacts
@app.get("/api/runs/{run_id}/artifacts")
def artifacts(run_id: str):
    p = run_path(run_id)
    return [{"name": f.relative_to(p).as_posix(), "bytes": f.stat().st_size} for f in sorted(p.rglob("*")) if f.is_file()]


@app.get("/api/runs/{run_id}/artifacts/{name:path}")
def artifact(run_id: str, name: str):
    p = run_path(run_id)
    f = (p / name).resolve()
    if p not in f.parents or not f.is_file():
        raise HTTPException(404, f"artifact not found: {name}")
    return FileResponse(f)


@app.get("/api/runs/{run_id}/zip")
def zip_run(run_id: str):
    p = run_path(run_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in p.rglob("*"):
            if f.is_file():
                z.write(f, f"{run_id}/{f.relative_to(p).as_posix()}")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'})


# ------------------------------------------------------------------ chat + regression
class ChatIn(BaseModel):
    run_id: str
    message: str


def _runtime(run_id: str) -> AgentRuntime:
    p = run_path(run_id)
    if not (p / "agent.yaml").exists():
        raise HTTPException(409, "this run has no agent.yaml (it failed before generation)")
    key = f"{run_id}:{(p / 'agent.yaml').stat().st_mtime}"
    if key not in AGENTS:
        docs = p / "docs" if (p / "docs").is_dir() else resolve_path(read_meta(p).get("docs_dir", ""))
        AGENTS[key] = AgentRuntime.load(p / "agent.yaml", docs)
    return AGENTS[key]


@app.post("/api/chat")
def chat(body: ChatIn):
    if not body.message.strip():
        raise HTTPException(400, "message is empty")
    r = _runtime(body.run_id).ask(body.message)
    d = r.model_dump()
    d["retrieved"] = [{k: x[k] for k in ("chunk_id", "doc", "confidence")} for x in d["retrieved"]]
    return d


@app.post("/api/runs/{run_id}/regress")
async def regress(run_id: str, files: list[UploadFile] = File(default=[]), demo_v2: bool = Form(False)):
    p = run_path(run_id)
    if not (p / "results_final.json").exists():
        raise HTTPException(409, "run has no final results to compare against")
    nd = p / "regress_docs"
    shutil.rmtree(nd, ignore_errors=True)
    nd.mkdir()
    if demo_v2:
        for f in (DEMOS["hr"] / "docs_v2").iterdir():
            shutil.copy2(f, nd / f.name)
    for f in files:
        name = Path(f.filename or "").name
        if name:
            (nd / name).write_bytes(await f.read())
    if not any(nd.iterdir()):
        raise HTTPException(400, "upload the changed documents")
    out = await asyncio.to_thread(run_regression, p, nd)
    return {"summary": out["summary"], "score_now": out["score_now"], "report": "regression_report.md"}


# ------------------------------------------------------------------ read-only endpoints for the UI
DEMO_INFO = {
    "hr": ("HR policy assistant", "Leave, conduct, travel and expenses for shore staff. The brief also asks for one topic the documents don't cover."),
    "spares": ("Ship-spares procurement", "A 64-row parts catalogue plus two supplier terms PDFs. Needs lookups and arithmetic."),
    "admissions": ("University admissions", "Deadlines, entry requirements, fees and scholarships across three formats."),
}
DEMO_ARTIFACTS = ["requirements.json", "requirements.md", "agent.yaml", "tools.json", "evalset.json", "iterations.json",
                  "results_final.json", "scorecard.json", "report.md", "judge_selftest.json", "meta.json"]


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _demo(demo_id: str) -> dict:
    if demo_id not in DEMOS:
        raise HTTPException(404, f"unknown demo {demo_id}; choose from {list(DEMOS)}")
    d = DEMOS[demo_id]
    title, subtitle = DEMO_INFO[demo_id]
    files = [{"name": f.name, "bytes": f.stat().st_size, "type": f.suffix.lstrip(".")} for f in sorted((d / "docs").iterdir()) if f.is_file()]
    return {"id": demo_id, "title": title, "subtitle": subtitle, "brief": (d / "brief.txt").read_text(encoding="utf-8").strip(), "files": files}


@app.get("/api/demos")
def demos():
    return [_demo(k) for k in DEMOS]


@app.post("/api/demos/{demo_id}/load")
def load_demo(demo_id: str):
    """Returns the demo brief and document list; the files are copied into the run when the build starts (demo=<id>)."""
    return _demo(demo_id)


def _run_dirs() -> list[Path]:
    return sorted((p for p in runs_dir().iterdir() if (p / "meta.json").exists()), key=lambda x: x.stat().st_mtime, reverse=True)


@app.get("/api/stats")
def stats():
    agents = cases = fixed = 0
    scores = []
    for p in _run_dirs():
        if (p / "agent.yaml").exists():
            agents += 1
        cases += len((_json(p / "evalset.json") or {}).get("cases", []))
        for it in (_json(p / "iterations.json") or {}).get("iterations", []):
            if it.get("decision") == "kept":
                fixed += len(it.get("newly_passing_ids", []))
        m = _json(p / "meta.json") or {}
        if m.get("status") == "completed" and m.get("heldout_score") is not None:
            scores.append(m["heldout_score"])
    return {"agents_built": agents, "eval_cases": cases, "issues_fixed": fixed, "runs_scored": len(scores),
            "avg_heldout_score": round(sum(scores) / len(scores), 1) if scores else None}


@app.get("/api/runs/{run_id}/bundle")
def bundle(run_id: str):
    """Every artifact the results dashboard needs, in one call."""
    p = run_path(run_id)
    st = RUNS.get(run_id)
    meta = read_meta(p)
    target = (meta.get("options") or {}).get("target_score")
    agent_yaml = (p / "agent.yaml").read_text(encoding="utf-8") if (p / "agent.yaml").exists() else None
    return {
        "run_id": run_id, "meta": meta, "done": st.done if st else True, "waiting": st.waiting if st else None,
        "target": target if target is not None else get_settings().target_score,
        "requirements": _json(p / "requirements.json"), "tools": _json(p / "tools.json"),
        "agent": yaml.safe_load(agent_yaml) if agent_yaml else None, "agent_yaml": agent_yaml,
        "evalset": _json(p / "evalset.json"), "iterations": _json(p / "iterations.json"),
        "tournament": _json(p / "tournament.json"), "results": _json(p / "results_final.json"),
        "scorecard": _json(p / "scorecard.json"), "selftest": _json(p / "judge_selftest.json"),
        "regression": _json(p / "regression.json"),
        "artifacts": sorted(f.relative_to(p).as_posix() for f in p.rglob("*") if f.is_file() and f.parent == p),
    }


def _check(rid, group, title, ui, fn, run: Path | None, evidence: list[str]):
    extra: list[str] = []
    try:
        res = fn(run) if run else ("fail", "no completed run yet - build one first")
        status, detail = res[0], res[1]
        extra = list(res[2]) if len(res) > 2 else []
    except Exception as e:  # a check that crashes is a failed check, not a crashed page
        status, detail = "fail", f"check error: {e}"
    links = [{"label": n, "url": f"/api/runs/{run.name}/artifacts/{n}"} for n in evidence if run and (run / n).exists()]
    for ref in extra:  # "<run_id>/<file>" evidence from another run
        rid_, name = ref.split("/", 1)
        if (runs_dir() / rid_ / name).exists():
            url = f"/api/runs/{rid_}/artifacts/{name}"
            if all(l["url"] != url for l in links):
                links.append({"label": ref, "url": url})
    return {"id": rid, "group": group, "title": title, "status": status, "detail": detail, "ui": ui, "evidence": links}


@app.get("/api/requirements-status")
def requirements_status(run_id: str | None = None):
    runs = _run_dirs()
    run = run_path(run_id) if run_id else next((p for p in runs if (p / "scorecard.json").exists() and (read_meta(p).get("status") == "completed")), None)
    J = lambda r, n: _json(r / n) or {}  # noqa: E731

    def r1(r):
        req = J(r, "requirements.json")
        n = len(req.get("clarifications", []))
        ok = all(k in req for k in ("scope", "audience", "tone", "must_answer", "must_refuse")) and n <= 5
        return ("pass" if ok else "fail", f"{n} clarifying question(s) asked (cap 5); {len(req.get('must_answer', []))} must-answer, {len(req.get('must_refuse', []))} must-refuse topics")

    def r2(r):
        flags = [f for f in J(r, "requirements.json").get("flags", []) if f.get("type") == "groundability"]
        bad = [f["topic"] for f in flags if f.get("verdict") == "unsupported"]
        return ("pass" if flags else "fail", f"{len(flags)} topics checked; unsupported -> must-refuse: {', '.join(bad) or 'none in this run'}")

    def r3(r):
        from forgeai.generator import load_agent
        a = load_agent(r / "agent.yaml")
        t = J(r, "tools.json")
        return ("pass", f"agent '{a.name}' with tools [{', '.join(a.tools) or 'none'}]; rejected [{', '.join(x['name'] for x in t.get('rejected', []))}]")

    def r4(r):
        s = J(r, "evalset.json").get("stats", {})
        return ("pass" if s.get("meets_minimums") else "partial", f"{s.get('total')} cases {s.get('by_type')}; uncovered docs: {s.get('docs_uncovered') or 'none'}")

    def r5(r):
        st = J(r, "judge_selftest.json")
        return ("pass" if st.get("all_correct") else "partial", f"self-test {st.get('n_correct')}/{st.get('n')}; deterministic checks + position-swapped LLM judge on '{read_meta(r).get('models', {}).get('judge')}'")

    def r6(r):
        it = J(r, "iterations.json")
        fixes = [i for i in it.get("iterations", []) if i.get("kind") == "fix"]
        return ("pass" if len(fixes) <= 3 and it.get("stop_reason") else "fail", f"{len(fixes)} fix iteration(s), {sum(i.get('decision', '').startswith('reverted') for i in fixes)} reverted; stop: {it.get('stop_reason')}")

    def r7(r):
        md = (r / "report.md").read_text(encoding="utf-8")
        ok = "What still fails and why" in md and "Known limits of this evaluation" in md
        return ("pass" if ok else "fail", "report has 'What still fails and why' and 'Known limits' sections" if ok else "report sections missing")

    def r8(r):
        from forgeai.generator import load_agent
        load_agent(r / "agent.yaml")
        docs = r / "docs" if (r / "docs").is_dir() else resolve_path(read_meta(r).get("docs_dir", ""))
        return ("pass" if docs.is_dir() else "partial", f"agent.yaml validates; documents {'found' if docs.is_dir() else 'missing'} for the chat runner")

    def r9(_r):
        missing = {}
        for name in ("hr_demo", "spares_demo", "admissions_demo"):
            d = next((b / name for b in (runs_dir(), ROOT / "runs") if (b / name).is_dir()), None)
            missing[name] = [a for a in DEMO_ARTIFACTS if not d or not (d / a).exists()]
        bad = {k: v for k, v in missing.items() if v}
        return ("pass" if not bad else "fail", "runs/hr_demo, runs/spares_demo, runs/admissions_demo complete" if not bad else f"missing: {bad}",
                [f"{n}/report.md" for n in missing])

    def any_run(pred):
        return next((p for p in runs if pred(p)), None)

    def s_tour(r):
        hit = r if (r / "tournament.json").exists() else any_run(lambda p: (p / "tournament.json").exists())
        return ("pass", f"winner '{J(hit, 'tournament.json').get('winner')}' in {hit.name}", [f"{hit.name}/tournament.json"]) if hit else ("partial", "available (--tournament) but not used in any run yet")

    def s_budget(r):
        u = read_meta(r).get("usage", {})
        return ("pass" if u.get("max_tokens") else "partial", f"{u.get('tokens')} of {u.get('max_tokens')} tokens, {u.get('elapsed_s')}s of {u.get('max_seconds')}s")

    def s_approve(r):
        hit = any_run(lambda p: '"approval_requested"' in (p / "events.jsonl").read_text(encoding="utf-8") if (p / "events.jsonl").exists() else False)
        return ("pass", f"approval checkpoint used in {hit.name}", [f"{hit.name}/events.jsonl"]) if hit else ("partial", "available (--approve / 'Review requirements first') but not used yet")

    def s_regress(r):
        hit = any_run(lambda p: (p / "regression_report.md").exists())
        return ("pass", f"regression report in {hit.name}", [f"{hit.name}/regression_report.md"]) if hit else ("partial", "available but no regression run yet")

    def s_seed(r):
        return ("pass" if read_meta(r).get("seed") is not None else "fail", f"seed {read_meta(r).get('seed')} stored in meta.json")

    core = [
        ("R1", "Intake interviewer", "Build › 1 Interview", r1, ["requirements.json", "requirements.md", "intake_dropped_questions.json"]),
        ("R2", "Groundability guard", "Build › 2 Groundability check", r2, ["requirements.json", "requirements.md"]),
        ("R3", "Agent generator + tool validator", "Results › Agent card", r3, ["agent.yaml", "tools.json"]),
        ("R4", "Eval generator", "Results › Eval cases", r4, ["evalset.json"]),
        ("R5", "Hybrid judge with bias defences", "Results › Judge self-test", r5, ["judge_selftest.json", "results_final.json"]),
        ("R6", "Critic-optimizer loop", "Results › Changelog", r6, ["iterations.json"]),
        ("R7", "Honest reporting", "Results › What still fails", r7, ["report.md", "scorecard.json"]),
        ("R8", "Runnable chat agent", "Chat", r8, ["agent.yaml"]),
        ("R9", "Demonstrations committed", "Runs", r9, []),
    ]
    stretch = [
        ("S1", "Prompt tournament + held-out split", "Results › Tournament", s_tour, ["tournament.json"]),
        ("S2", "Budget enforcement", "Results › Budget", s_budget, ["meta.json"]),
        ("S3", "Human checkpoint", "Build › Approve requirements", s_approve, ["events.jsonl"]),
        ("S4", "Regression mode", "Runs › Regression", s_regress, ["regression_report.md"]),
        ("S5", "Reproducibility (seed)", "Results › header", s_seed, ["meta.json"]),
    ]
    items = [_check(i, "core", t, u, f, run, e) for i, t, u, f, e in core]
    items += [_check(i, "stretch", t, u, f, run, e) for i, t, u, f, e in stretch]
    return {"run_id": run.name if run else None, "items": items}


app.mount("/", StaticFiles(directory=str(ROOT / "web"), html=True), name="web")
