"""Orchestrator. Emits structured events; every stage is wrapped so the run never crashes and always
leaves a report.md explaining how far it got."""
from __future__ import annotations

import datetime as dt
import json
import random
import shutil
import time
import traceback
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .evalgen import generate_evalset
from .generator import build_agent, save_agent
from .groundability import check_groundability
from .ingest import chunk_all, load_folder
from .intake import requirements_md, run_intake, write_requirements
from .judge import judge_selftest
from .llm import LLM, Budget, BudgetExceeded
from .config import ROOT, get_settings
from .optimizer import optimize, run_eval
from .report import write_report
from .retrieval import Retriever, calibrate_threshold
from .schemas import Requirements
from .tournament import run_tournament

# approval_fn(requirements) -> ("approve"|"edit"|"reject", edited_requirements_dict_or_None)
ApprovalFn = Callable[[Requirements], "tuple[str, dict | None]"]


@dataclass
class RunOptions:
    non_interactive: bool = True
    approve: bool = False
    tournament: bool = False
    seed: int = 42
    max_tokens: int | None = None
    max_seconds: float | None = None
    max_iterations: int = 3
    target_score: float | None = None
    judge_mode: str = "hybrid"


class StageFailed(Exception):
    def __init__(self, stage: str, err: BaseException):
        super().__init__(f"{stage}: {err}")
        self.stage, self.err = stage, err


class Rejected(Exception):
    pass


class Pipeline:
    def __init__(self, brief: str, docs_dir: str | Path, run_dir: str | Path, options: RunOptions | None = None,
                 emit: Callable | None = None, answer_fn: Callable | None = None, approval_fn: ApprovalFn | None = None,
                 llm: LLM | None = None):
        self.brief = brief.strip()
        self.docs_dir = Path(docs_dir).resolve()
        self.run_dir = Path(run_dir)
        self.opt = options or RunOptions()
        self._emit_ext = emit
        self.answer_fn = None if self.opt.non_interactive else answer_fn
        self.approval_fn = approval_fn if self.opt.approve else None
        s = get_settings()
        self.settings = s
        self.budget = Budget(self.opt.max_tokens or s.max_tokens_per_run, self.opt.max_seconds or s.max_seconds_per_run)
        self.caps = (self.budget.max_tokens, self.budget.max_seconds)
        self.llm = llm or LLM(s, self.budget)
        if llm is not None:
            self.llm.budget = self.budget
        self.ctx: dict = {"run_id": self.run_dir.name, "status": "running", "stages": []}

    # ------------------------------------------------------------ events
    def emit(self, type_: str, **data) -> None:
        ev = {"type": type_, "ts": dt.datetime.now().isoformat(timespec="seconds"), **data}
        try:
            with open(self.run_dir / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, default=str) + "\n")
        except OSError:
            pass
        if self._emit_ext:
            try:
                self._emit_ext(ev)
            except Exception:
                pass

    def _stage(self, name: str, fn: Callable, critical: bool = True):
        self.emit("stage_started", stage=name)
        t0, s0 = time.monotonic(), self.llm.snapshot()
        try:
            out = fn()
        except (Rejected, StageFailed):
            raise
        except BudgetExceeded as e:
            self.emit("error", stage=name, message=str(e), kind="budget")
            if critical:
                raise StageFailed(name, e) from e
            return None
        except Exception as e:
            self.emit("error", stage=name, message=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:])
            if critical:
                raise StageFailed(name, e) from e
            return None
        rec = {"stage": name, "seconds": round(time.monotonic() - t0, 2), "tokens": self.llm.snapshot()["tokens"] - s0["tokens"]}
        self.ctx["stages"].append(rec)
        self.emit("stage_done", **rec)
        return out

    def _write(self, name: str, obj) -> None:
        (self.run_dir / name).write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")

    def _usage(self) -> dict:
        st = self.llm.stats
        return {"tokens": st["tokens_in"] + st["tokens_out"], "calls": st["calls"], "max_tokens": self.caps[0],
                "elapsed_s": round(self.budget.elapsed(), 1), "max_seconds": self.caps[1],
                "fallbacks": st["fallbacks"], "validation_retries": st["validation_retries"],
                "transport_retries": st["transport_retries"], "cache_hits": st["cache_hits"], "by_task": st["by_task"]}

    # ------------------------------------------------------------ run
    def run(self) -> dict:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "events.jsonl").write_text("", encoding="utf-8")
        random.seed(self.opt.seed)
        np.random.seed(self.opt.seed)
        meta = {"run_id": self.run_dir.name, "brief": self.brief, "docs_dir": portable_path(self.docs_dir), "seed": self.opt.seed,
                "options": asdict(self.opt), "provider": self.settings.provider,
                "models": {"agent": self.llm.model_for("agent"), "judge": self.llm.model_for("judge")},
                "started_at": dt.datetime.now().isoformat(timespec="seconds")}
        self.ctx["meta"] = meta
        self._write("meta.json", meta)
        (self.run_dir / "brief.txt").write_text(self.brief, encoding="utf-8")
        try:
            self._run()
            self.ctx["status"] = "completed"
        except Rejected:
            self.ctx["status"] = "rejected"
            self.ctx["stop_reason"] = "requirements rejected by the requester"
        except StageFailed as e:
            self.ctx["status"] = "failed"
            self.ctx["error"] = {"stage": e.stage, "message": f"{type(e.err).__name__}: {e.err}"}
        except Exception as e:  # last line of defence
            self.ctx["status"] = "failed"
            self.ctx["error"] = {"stage": "pipeline", "message": f"{type(e).__name__}: {e}"}
        self.ctx["usage"] = self._usage()
        write_report(self.run_dir, self.ctx)
        meta.update(status=self.ctx["status"], finished_at=dt.datetime.now().isoformat(timespec="seconds"),
                    stop_reason=self.ctx.get("stop_reason"), usage=self.ctx["usage"],
                    heldout_score=self.ctx.get("final", {}).get("heldout", {}).get("score"),
                    dev_score=self.ctx.get("final", {}).get("dev", {}).get("score"), error=self.ctx.get("error"))
        self._write("meta.json", meta)
        summary = {k: meta.get(k) for k in ("run_id", "status", "heldout_score", "dev_score", "stop_reason", "error")}
        self.emit("finished", **summary)
        return summary

    def _run(self) -> None:
        s = self.opt
        # 1. ingest
        def ingest():
            docs, warnings = load_folder(self.docs_dir)
            if not docs:
                raise ValueError("no usable documents: " + "; ".join(warnings))
            return docs, warnings
        docs, warnings = self._stage("ingest", ingest)
        self.ctx["ingest_warnings"] = warnings
        if warnings:
            self.emit("flags", kind="ingest_warnings", warnings=warnings)
        self.docs = docs
        base_ret = Retriever(chunk_all(docs, 700, 110), 0.5)
        thr, _ = calibrate_threshold(base_ret, 4, s.seed)

        # 2. intake
        req, infos, dropped = self._stage("intake", lambda: run_intake(self.brief, docs, self.llm, self.answer_fn, self.emit))
        self._write("doc_inventory.json", infos)

        # 3. groundability guard
        req, flags = self._stage("groundability", lambda: check_groundability(req, base_ret, self.llm, thr, self.brief))
        self.emit("flags", kind="groundability", flags=flags)
        write_requirements(req, self.run_dir)
        self._write("intake_dropped_questions.json", dropped)

        # 4. human checkpoint
        if self.approval_fn:
            while True:
                self.emit("approval_requested", requirements=req.model_dump(), markdown=requirements_md(req))
                decision, edited = self.approval_fn(req)
                self.emit("log", message=f"approval decision: {decision}")
                if decision == "reject":
                    raise Rejected()
                if decision == "edit" and edited:
                    try:
                        req = Requirements.model_validate({**edited, "flags": []})
                    except Exception as e:  # invalid edit -> show the error and ask again
                        self.emit("error", stage="approval", message=f"edited requirements invalid: {e}", recoverable=True)
                        continue
                    req, flags = check_groundability(req, base_ret, self.llm, thr, self.brief)
                    self.emit("flags", kind="groundability", flags=flags)
                    write_requirements(req, self.run_dir)
                    continue
                break
        self.ctx["requirements"] = req.model_dump()

        # 5. generate agent
        agent, tool_log = self._stage("generate", lambda: build_agent(self.brief, req, docs, infos, self.llm, s.seed))
        self.ctx["tool_log"] = tool_log
        self.ctx["agent"] = agent.model_dump()
        self._write("tools.json", tool_log)
        save_agent(agent, self.run_dir / "agent_v0.yaml")
        save_agent(agent, self.run_dir / "agent.yaml")
        self.emit("flags", kind="tools", attached=[t["name"] for t in tool_log["attached"]],
                  rejected=[{"name": t["name"], "reason": t["reason"]} for t in tool_log["rejected"]])

        # 6. eval set
        def evals():
            chunks = chunk_all(docs, agent.chunk_size, agent.chunk_overlap)
            ret = Retriever(chunks, agent.hybrid_weight)
            return generate_evalset(docs, chunks, ret, req, agent.refusal_threshold, self.llm, s.seed)
        cases, elog = self._stage("evalgen", evals)
        self._write("evalset.json", {"stats": elog["stats"], "cases": [c.model_dump() for c in cases], "dropped": elog["dropped"]})
        self.ctx["eval_stats"], self.ctx["eval_dropped"] = elog["stats"], len(elog["dropped"])
        dev = [c for c in cases if c.split == "dev"]
        held = [c for c in cases if c.split == "heldout"]

        # 7. judge self-test (proves the judge catches known-bad answers)
        st = self._stage("judge_selftest", lambda: judge_selftest(self.llm, s.judge_mode), critical=False)
        if st:
            self.ctx["selftest"] = st
            self._write("judge_selftest.json", st)

        evaluate = lambda a: run_eval(a, docs, dev, self.llm, judge_mode=s.judge_mode)  # noqa: E731

        # 8. tournament (optional)
        baseline = None
        if s.tournament:
            out = self._stage("tournament", lambda: run_tournament(agent, req, infos, self.llm, evaluate, self.emit), critical=False)
            if out:
                agent, baseline, trec = out
                self.ctx["tournament"] = trec
                self._write("tournament.json", trec)

        # 9. critic-optimizer loop on dev
        target = s.target_score if s.target_score is not None else self.settings.target_score
        opt = self._stage("optimize", lambda: optimize(agent, evaluate, self.llm, s.max_iterations, target, self.emit, baseline), critical=False)
        if opt:
            agent = opt["agent"]
            self.ctx["iterations"], self.ctx["stop_reason"] = opt["iterations"], opt["stop_reason"]
        else:
            self.ctx["stop_reason"] = "optimizer failed or budget exhausted; shipping the pre-optimizer agent"
        self._write("iterations.json", {"stop_reason": self.ctx["stop_reason"], "iterations": self.ctx.get("iterations", [])})
        self.ctx["agent"] = agent.model_dump()
        save_agent(agent, self.run_dir / "agent.yaml")

        # 10. final evaluation: held-out is the number we report. Budget stops OPTIMISATION, never the
        # measurement - a report without a held-out score would hide what the budget cut off.
        try:
            self.budget.check()
        except BudgetExceeded as e:
            self.ctx["budget_grace"] = f"{e}; final evaluation ran past the budget so the report has a held-out score"
            self.emit("log", message=self.ctx["budget_grace"])
            self.budget.max_tokens = self.budget.max_seconds = 0

        def final():
            d = opt["final_eval"] if opt else run_eval(agent, docs, dev, self.llm, judge_mode=s.judge_mode)
            h = run_eval(agent, docs, held, self.llm, judge_mode=s.judge_mode)
            return {"dev": d, "heldout": h}
        fin = self._stage("final_eval", final, critical=False)
        if fin:
            self.ctx["final"] = fin
            self._write("results_final.json", {"dev_score": fin["dev"]["score"], "heldout_score": fin["heldout"]["score"],
                                               "results": fin["dev"]["results"] + fin["heldout"]["results"]})


def portable_path(p: Path) -> str:
    """Store paths inside the repo relative to it, so committed runs work on any machine."""
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def resolve_path(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"


def copy_docs(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for p in Path(src).iterdir():
        if p.is_file():
            shutil.copy2(p, dst / p.name)
