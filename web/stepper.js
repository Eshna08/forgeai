// Pipeline stepper: maps backend stage events onto 7 human steps with status, timing and a plain-English "why".
import { esc, icon, term } from "./ui.js";

export const STEPS = [
  { id: 1, title: "Interview", stages: ["ingest", "intake"], why: "Reads your documents and asks up to 5 questions so the agent fits your needs." },
  { id: 2, title: "Groundability check", stages: ["groundability"], why: "Checks every topic against your documents. Gaps become polite refusals, not guesses." },
  { id: 3, title: "Generate agent", stages: ["generate"], why: "Writes the system prompt, keeps only the tools the brief needs, tunes retrieval." },
  { id: 4, title: "Generate evals", stages: ["evalgen"], why: "Writes 24+ test questions from your documents and verifies every expected fact word-for-word." },
  { id: 5, title: "Judge", stages: ["judge_selftest"], why: "Proves the grader works: it must catch planted good and bad answers before grading yours." },
  { id: 6, title: "Improve", stages: ["tournament", "optimize"], why: "Runs the tests, diagnoses each failure, applies one targeted fix at a time (max 3)." },
  { id: 7, title: "Report", stages: ["final_eval"], why: "Scores questions the optimizer never saw and writes an honest report of what still fails." },
];
const LAST = { 1: "intake", 2: "groundability", 3: "generate", 4: "evalgen", 5: "judge_selftest", 6: "optimize", 7: "final_eval" };
const NON_CRITICAL = new Set(["judge_selftest", "tournament", "optimize", "final_eval", "approval"]);
const STAGE_STEP = Object.fromEntries(STEPS.flatMap((s) => s.stages.map((st) => [st, s.id])));
STAGE_STEP.approval = 2;
export const STAGE_TITLE = { ingest: "Reading documents", intake: "Interview", groundability: "Groundability check", generate: "Generate agent",
  evalgen: "Generate evals", judge_selftest: "Judge self-test", tournament: "Prompt tournament", optimize: "Improve", final_eval: "Final scoring", approval: "Approval" };

const parseTs = (ts) => (ts ? new Date(ts) : new Date());
const fmtSecs = (s) => (s < 60 ? `${Math.max(0, Math.round(s))}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`);

export class Stepper {
  constructor(el) {
    this.el = el;
    this.state = Object.fromEntries(STEPS.map((s) => [s.id, { status: "waiting", start: null, end: null, note: "", warn: false }]));
    this.live = true;
    el.innerHTML = `<ol class="stepper" aria-label="Pipeline progress">${STEPS.map((s) => `
      <li class="step" data-step="${s.id}" data-status="waiting">
        <div class="num" aria-hidden="true">${s.id}</div>
        <div class="title">${s.id} ${esc(s.title)}</div>
        <div class="state" aria-live="polite">Waiting</div>
        <div class="why">${s.id === 6 ? s.why.replace("diagnoses each failure", `diagnoses each ${term("prompt defect", "failure")}`) : esc(s.why)}</div>
      </li>`).join("")}</ol>`;
    this.timer = setInterval(() => this.paint(), 1000);
  }

  destroy() { clearInterval(this.timer); }

  set(id, patch) { Object.assign(this.state[id], patch); this.paint(); }

  waitingForUser(id, note) { this.set(id, { status: "waiting-user", note }); }

  handle(ev) {
    const ts = parseTs(ev.ts);
    const stepId = STAGE_STEP[ev.stage];
    const st = stepId && this.state[stepId];
    switch (ev.type) {
      case "stage_started":
        if (st) {
          if (!st.start) st.start = ts;
          if (st.status !== "failed") st.status = "running";
          if (ev.stage === "tournament") st.note = "Prompt tournament: 3 strategies";
          for (const s of STEPS) if (s.id < stepId && this.state[s.id].status === "running") this.state[s.id].status = this.state[s.id].warn ? "warning" : "done";
        }
        break;
      case "stage_done":
        if (st && LAST[stepId] === ev.stage) { st.end = ts; st.status = st.warn ? "warning" : "done"; }
        if (ev.stage === "intake" && st && !st.note) st.note = "Requirements written";
        break;
      case "questions_asked":
        this.state[1].note = ev.questions.length ? `${ev.questions.length} question${ev.questions.length > 1 ? "s" : ""} asked` : "No questions needed";
        break;
      case "flags":
        if (ev.kind === "groundability") {
          const f = ev.flags || [];
          const c = (v) => f.filter((x) => x.verdict === v).length;
          const gaps = c("unsupported") + c("tool_gap");
          this.state[2].note = `${c("supported")} supported · ${c("partial")} partial · ${gaps} gap${gaps === 1 ? "" : "s"}`;
          this.state[2].warn = gaps + c("partial") > 0;
          if (this.state[2].warn && this.state[2].status === "done") this.state[2].status = "warning";
        }
        if (ev.kind === "tools") this.state[3].note = `Tools: ${ev.attached.join(", ") || "none"}`;
        break;
      case "approval_requested":
        if (this.live) { this.state[2].status = "waiting-user"; this.state[2].note = "Waiting for your approval"; }
        break;
      case "log":
        if (/approval decision: approve/.test(ev.message || "")) { this.state[2].status = this.state[2].warn ? "warning" : "done"; this.state[2].note = "Approved by you"; }
        break;
      case "iteration_result": {
        const s6 = this.state[6];
        s6.note = ev.iteration === 0 ? `Baseline ${ev.score_after}%` : `Iteration ${ev.iteration} of 3 · ${(ev.category || "").replace("_", " ")} · ${ev.score_before}→${ev.score_after}% ${ev.decision?.startsWith("reverted") ? "(reverted)" : ""}`;
        break;
      }
      case "error":
        if (st) {
          if (NON_CRITICAL.has(ev.stage) || ev.recoverable) { st.warn = true; st.note = "Problem: " + (ev.message || "").slice(0, 80); }
          else { st.status = "failed"; st.note = (ev.message || "failed").slice(0, 90); st.end = ts; }
        }
        break;
      case "finished":
        if (ev.status === "rejected") {
          this.state[2].status = "failed"; this.state[2].note = "Rejected by you";
        } else if (ev.status === "failed") {
          for (const s of STEPS) if (this.state[s.id].status === "running") this.state[s.id].status = "failed";
        } else {
          for (const s of STEPS) {
            const x = this.state[s.id];
            if (x.status === "running") { x.status = x.warn ? "warning" : "done"; x.end = x.end || ts; }
          }
        }
        for (const s of STEPS) if (this.state[s.id].status === "waiting") this.state[s.id].status = "skipped";
        this.live = false;
        break;
      default:
    }
    this.paint();
  }

  paint() {
    const now = new Date();
    for (const s of STEPS) {
      const x = this.state[s.id];
      const li = this.el.querySelector(`[data-step="${s.id}"]`);
      if (!li) continue;
      li.dataset.status = x.status;
      const secs = x.start ? ((x.end || (x.status === "running" || x.status === "waiting-user" ? now : x.start)) - x.start) / 1000 : 0;
      const label = { waiting: "Waiting", running: `Running · ${fmtSecs(secs)}`, "waiting-user": "Needs you", done: `Done · ${fmtSecs(secs)}`,
        warning: `Done with warnings · ${fmtSecs(secs)}`, failed: "Failed", skipped: "Skipped" }[x.status];
      li.querySelector(".state").textContent = x.note ? `${label} — ${x.note}` : label;
      const num = li.querySelector(".num");
      const ic = { done: "check", warning: "warn", failed: "x", "waiting-user": "user" }[x.status];
      num.innerHTML = ic ? icon(ic) : String(s.id);
      li.setAttribute("aria-label", `Step ${s.id}, ${s.title}: ${li.querySelector(".state").textContent}`);
    }
  }
}
