// Live run: stepper + activity feed + interactive panels (intake, groundability, approval), then results.
import { api, streamEvents } from "../api.js";
import { Stepper, STAGE_TITLE } from "../stepper.js";
import { esc, icon, openModal, skeleton, term, toast } from "../ui.js";
import { renderAgentCard, renderResults } from "./results.js";

let stopStream = null;
let stepper = null;

export function unmount() {
  if (stopStream) stopStream();
  if (stepper) stepper.destroy();
  stopStream = stepper = null;
}

const time = (ts) => (ts ? ts.slice(11, 19) : "");

function describe(ev) {
  const s = STAGE_TITLE[ev.stage] || ev.stage;
  switch (ev.type) {
    case "stage_started": return { ico: "play", text: `Started: ${s}` };
    case "stage_done": return { ico: "check", kind: "ok", text: `Finished ${s} in ${ev.seconds}s${ev.tokens ? ` · ${ev.tokens.toLocaleString()} tokens` : ""}` };
    case "questions_asked": {
      const d = (ev.dropped || []).length;
      return { ico: "chat", text: ev.questions.length ? `ForgeAI has ${ev.questions.length} clarifying question${ev.questions.length > 1 ? "s" : ""}${d ? ` (dropped ${d} it could answer itself or over the cap of 5)` : ""}.` : "No clarifying questions needed." };
    }
    case "flags":
      if (ev.kind === "groundability") {
        const f = ev.flags || [];
        const gaps = f.filter((x) => x.verdict === "unsupported" || x.verdict === "tool_gap");
        return { ico: "shield", kind: gaps.length ? "warn" : "ok", text: `Checked ${f.filter((x) => x.type === "groundability").length} topics against your documents.${gaps.length ? ` ${gaps.length} not covered: ${gaps.map((g) => g.topic || g.capability).join("; ")}. The agent will refuse these.` : " All covered."}` };
      }
      if (ev.kind === "tools") return { ico: "tool", text: `Tools attached: ${ev.attached.join(", ") || "none"}. Rejected: ${ev.rejected.map((r) => `${r.name} (${r.reason})`).join("; ") || "none"}.` };
      return { ico: "warn", kind: "warn", text: `Heads-up about your files: ${(ev.warnings || []).join("; ")}` };
    case "approval_requested": return { ico: "user", kind: "warn", text: "Paused: waiting for you to approve the requirements." };
    case "iteration_result":
      if (ev.iteration === 0) return { ico: "chart", text: `Baseline score on the dev questions: ${ev.score_after}%.` };
      return { ico: "wand", kind: ev.decision?.startsWith("reverted") ? "warn" : "ok", text: `Improvement ${ev.iteration}: targeted ${(ev.category || "").replace("_", " ")} · ${ev.score_before}% → ${ev.score_after}% · ${ev.decision}.` };
    case "log": return { ico: "info", text: ev.message };
    case "error": return { ico: "warn", kind: "bad", text: `Problem in ${s}: ${ev.message}${ev.kind === "budget" ? " (budget limit reached: raise MAX_TOKENS_PER_RUN / MAX_SECONDS_PER_RUN in .env)" : ""}` };
    case "finished":
      if (ev.status === "completed") return { ico: "flag", kind: "ok", text: `Done. Held-out score ${ev.heldout_score}%, dev score ${ev.dev_score}%.` };
      if (ev.status === "rejected") return { ico: "x", kind: "warn", text: "Stopped: you rejected the requirements. Nothing was generated." };
      return { ico: "x", kind: "bad", text: `The run stopped early${ev.error ? ` in ${ev.error.stage}: ${ev.error.message}` : ""}. A partial report explains what happened.` };
    default: return null;
  }
}

const GVERDICT = {
  supported: ["check", "Supported", "Nothing to do: the agent will answer this from your documents."],
  partial: ["warn", "Partially supported", "Add a document with the specifics, or accept that the agent only answers what is written."],
  unsupported: ["x", "Not in your documents, so the agent will refuse this", "Upload a document that covers it and rebuild, or keep it as a refusal."],
  tool_gap: ["x", "Needs a capability ForgeAI doesn't have", "Handle this outside the agent, or remove it from the brief. Requests for it will be refused."],
};

function groundCards(flags) {
  return `<div class="card"><div class="card-head"><div class="badge-icon">${icon("shield")}</div><div><h3>Groundability check</h3>
    <p>Each topic you asked for, checked against your documents by ${term("retrieval")} and a second model. Gaps become refusals.</p></div></div>
    <div class="grid grid-2" style="gap:12px">${flags.map((f) => {
      const v = f.verdict in GVERDICT ? f.verdict : "partial";
      const [ic, label, todo] = GVERDICT[v];
      const conf = f.retrieval_confidence != null ? `<div class="small muted">Retrieval confidence ${Math.round(f.retrieval_confidence * 100)}% (threshold ${Math.round((f.threshold || 0) * 100)}%)</div>` : "";
      return `<div class="gcard ${v}"><div class="gtitle">${icon(ic)}<span>${esc(f.topic || f.capability)}</span></div>
        <div class="verdict">${label}</div><p>${esc(f.reason || f.message || "")}</p>${conf}<p class="todo"><strong>What you can do:</strong> ${todo}</p></div>`;
    }).join("")}</div></div>`;
}

function intakeCard(runId, questions, onDone) {
  const el = document.createElement("div");
  el.className = "card";
  const answers = [];
  const n = questions.length;
  const paint = () => {
    const i = answers.length;
    const history = questions.slice(0, i).map((q, k) => `<div class="bubble bot"><div class="who">${icon("bot")}ForgeAI</div>${esc(q)}</div>
      <div class="bubble user"><div class="who">You</div>${answers[k] ? esc(answers[k]) : "<em>ForgeAI will answer this one</em>"}</div>`).join("");
    const done = i >= n;
    el.innerHTML = `<div class="card-head"><div class="badge-icon">${icon("chat")}</div><div><h3>A few quick questions</h3>
      <p>Answers shape the agent's audience, tone and refusals. Skip any you don't care about.</p></div></div>
      <div class="row small" style="margin-bottom:8px"><span id="q-progress" aria-live="polite">${done ? "All questions answered" : `Question ${i + 1} of ${n}`}</span><span class="spacer"></span>
      <button class="btn btn-ghost btn-sm" type="button" data-auto>${icon("wand")}Let ForgeAI answer for me</button></div>
      <div class="progress" aria-hidden="true"><span style="width:${(i / n) * 100}%"></span></div>
      <div class="bubbles" style="margin-top:14px">${history}${done ? "" : `<div class="bubble bot"><div class="who">${icon("bot")}ForgeAI · question ${i + 1} of ${n}</div>${esc(questions[i])}</div>`}</div>
      ${done ? `<div class="row" style="margin-top:14px"><button class="btn btn-primary" type="button" data-send>${icon("check")}Send answers</button>
        <button class="btn btn-ghost" type="button" data-redo>Start over</button></div>` : `
      <form class="composer" style="padding:12px 0 0;border:0" data-form>
        <label class="sr-only" for="q-answer">Your answer to question ${i + 1}</label>
        <input class="input" id="q-answer" autocomplete="off" placeholder="Type your answer…">
        <button class="btn btn-primary" type="submit">Answer</button>
      </form>
      <button class="btn btn-ghost btn-sm" type="button" data-skip>Skip: let ForgeAI answer this one</button>`}`;
    el.querySelector("[data-auto]").addEventListener("click", () => send(true));
    if (done) {
      el.querySelector("[data-send]").addEventListener("click", () => send(false));
      el.querySelector("[data-redo]").addEventListener("click", () => { answers.length = 0; paint(); });
    } else {
      const input = el.querySelector("#q-answer");
      el.querySelector("[data-form]").addEventListener("submit", (e) => { e.preventDefault(); answers.push(input.value.trim() || null); paint(); el.querySelector("#q-answer, [data-send]")?.focus(); });
      el.querySelector("[data-skip]").addEventListener("click", () => { answers.push(null); paint(); el.querySelector("#q-answer, [data-send]")?.focus(); });
    }
  };
  const send = async (auto) => {
    try {
      await api.answers(runId, auto ? [] : answers, auto);
      el.innerHTML = `<div class="callout ok">${icon("check")}<p>${auto ? "ForgeAI will answer the questions itself." : "Answers sent."} Writing the requirements now.</p></div>`;
      onDone();
    } catch (e) { toast(`Couldn't send answers: ${e.message}`, "bad"); }
  };
  paint();
  return el;
}

function approvalCard(runId, req, onDone) {
  const el = document.createElement("div");
  el.className = "card";
  let mustAnswer = [...(req.must_answer || [])], mustRefuse = [...(req.must_refuse || [])];
  const chips = (list, key) => list.map((t, i) => `<span class="chip chip-static">${esc(t)}<button class="x" type="button" data-rm="${key}:${i}" aria-label="Remove ${esc(t)}">×</button></span>`).join("");
  const paint = () => {
    el.innerHTML = `<div class="card-head"><div class="badge-icon">${icon("user")}</div><div><h3>Review the requirements</h3>
      <p>Nothing is generated until you decide. You're the expert: approving here stops ForgeAI from building on a misunderstanding.</p></div></div>
      <div class="callout warn" style="margin-bottom:14px">${icon("clock")}<p>Generation is paused. Edits re-run the groundability check before you approve.</p></div>
      <form class="stack" data-form>
        <div><label class="field" for="rq-title">Name</label><input class="input" id="rq-title" value="${esc(req.title)}"></div>
        <div><label class="field" for="rq-scope">Scope</label><textarea class="input" id="rq-scope" rows="3">${esc(req.scope)}</textarea></div>
        <div class="grid grid-2" style="gap:12px">
          <div><label class="field" for="rq-aud">Audience</label><input class="input" id="rq-aud" value="${esc(req.audience)}"></div>
          <div><label class="field" for="rq-tone">Tone</label><input class="input" id="rq-tone" value="${esc(req.tone)}"></div>
        </div>
        <div><span class="field">Must answer</span><div class="chips">${chips(mustAnswer, "a")}</div>
          <div class="row" style="margin-top:8px"><label class="sr-only" for="add-a">Add a topic to answer</label><input class="input" id="add-a" placeholder="Add a topic…" style="flex:1;min-width:0"><button class="btn btn-secondary btn-sm" type="button" data-add="a">Add</button></div></div>
        <div><span class="field">Must refuse</span><div class="chips">${chips(mustRefuse, "r")}</div>
          <div class="row" style="margin-top:8px"><label class="sr-only" for="add-r">Add a topic to refuse</label><input class="input" id="add-r" placeholder="Add a topic…" style="flex:1;min-width:0"><button class="btn btn-secondary btn-sm" type="button" data-add="r">Add</button></div></div>
        <div class="row">
          <button class="btn btn-primary" type="button" data-act="approve">${icon("check")}Approve and build</button>
          <button class="btn btn-secondary" type="button" data-act="edit">Save edits and re-check</button>
          <button class="btn btn-danger" type="button" data-act="reject">Reject</button>
        </div>
        <span class="helper">Approve continues with what you see. Save edits re-validates your changes and runs the groundability check again. Reject stops the build.</span>
      </form>`;
    el.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => {
      const [k, i] = b.dataset.rm.split(":"); (k === "a" ? mustAnswer : mustRefuse).splice(+i, 1); keep(); paint();
    }));
    el.querySelectorAll("[data-add]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.add, inp = el.querySelector(`#add-${k}`);
      if (inp.value.trim()) { (k === "a" ? mustAnswer : mustRefuse).push(inp.value.trim()); keep(); paint(); }
    }));
    el.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.dataset.act)));
  };
  const keep = () => {
    const v = (s) => el.querySelector(s)?.value;
    Object.assign(req, { title: v("#rq-title") ?? req.title, scope: v("#rq-scope") ?? req.scope, audience: v("#rq-aud") ?? req.audience, tone: v("#rq-tone") ?? req.tone });
  };
  const act = async (action) => {
    keep();
    if (action === "edit" && !mustAnswer.length) { toast("Keep at least one topic in 'Must answer'.", "warn"); return; }
    if (action === "reject") {
      const m = openModal(`<h2>Reject these requirements?</h2><p>The build stops and nothing is generated. You can start a new build with a different brief.</p>
        <div class="row"><button class="btn btn-danger" type="button" id="yes-reject">Yes, reject</button><button class="btn btn-ghost" type="button" id="no-reject">Keep reviewing</button></div>`, { label: "Confirm reject" });
      m.el.querySelector("#no-reject").addEventListener("click", m.close);
      m.el.querySelector("#yes-reject").addEventListener("click", async () => { m.close(); await send("reject"); });
      return;
    }
    await send(action);
  };
  const send = async (action) => {
    try {
      const edited = action === "edit" ? { ...req, must_answer: mustAnswer, must_refuse: mustRefuse } : null;
      await api.approval(runId, action, edited);
      el.innerHTML = `<div class="callout ${action === "reject" ? "warn" : "ok"}">${icon(action === "reject" ? "x" : "check")}<p>${{ approve: "Approved. Generating the agent now.", edit: "Edits saved. Re-running the groundability check; you'll be asked to approve again.", reject: "Rejected. The build is stopping." }[action]}</p></div>`;
      onDone(action);
    } catch (e) { toast(`Couldn't send your decision: ${e.message}`, "bad"); }
  };
  paint();
  return el;
}

export async function mount(root, { param: id }) {
  root.innerHTML = `<div class="wrap section">${skeleton(4)}</div>`;
  const info = await api.run(id);
  const meta = info.meta || {};
  const opts = meta.options || {};
  const live = !info.done;
  root.innerHTML = `
  <div class="wrap">
    <div class="page-head">
      <span class="eyebrow">Run</span>
      <h1>${live ? "Building your agent" : "Build results"}</h1>
      <p>${esc((meta.brief || "").slice(0, 260))}</p>
      <div class="row small">
        <span class="pill mono">${esc(id)}</span>
        <span class="pill" id="run-status">${live ? "Running" : esc(meta.status || "finished")}</span>
        <span class="pill">${opts.non_interactive ? "Unattended" : "Interactive"}</span>
        ${opts.approve ? '<span class="pill">Requirements review</span>' : ""}${opts.tournament ? '<span class="pill">Prompt tournament</span>' : ""}
        <span class="pill">seed ${esc(meta.seed ?? opts.seed ?? "–")}</span>
        <span class="pill">${esc(meta.provider || "")}</span>
      </div>
    </div>
    <section aria-label="Pipeline progress" id="stepper"></section>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));margin-top:var(--s5);align-items:start">
      <div class="stack" id="panels">
        <div id="intake-slot"></div><div id="approval-slot"></div><div id="ground-slot"></div><div id="agent-slot"></div>
      </div>
      <section class="card" aria-labelledby="feed-title">
        <div class="card-head"><div class="badge-icon">${icon("list")}</div><div><h3 id="feed-title">Activity</h3><p>Everything ForgeAI does, in plain English.</p></div></div>
        <ol class="feed" id="feed" aria-live="polite" tabindex="0" aria-label="Activity feed"></ol>
      </section>
    </div>
    <div id="results" style="margin:var(--s7) 0 var(--s9)"></div>
  </div>`;

  stepper = new Stepper(root.querySelector("#stepper"));
  stepper.live = live;
  const feed = root.querySelector("#feed");
  const $ = (s) => root.querySelector(s);
  let finished = false;

  const showAgent = async () => {
    try { const b = await api.bundle(id); if (b.agent) renderAgentCard($("#agent-slot"), b); } catch {}
  };
  const finish = async (ev) => {
    if (finished) return;
    finished = true;
    $("#intake-slot").innerHTML = "";
    $("#approval-slot").innerHTML = "";
    const st = ev ? ev.status : "unknown";
    $("#run-status").textContent = st;
    $("#run-status").className = `pill ${st === "completed" ? "ok" : st === "rejected" ? "warn" : "bad"}`;
    root.querySelector(".page-head h1").textContent = st === "completed" ? "Build results" : st === "rejected" ? "Build stopped" : "Build stopped early";
    $("#results").innerHTML = skeleton(5);
    try {
      const b = await api.bundle(id);
      if (b.agent) renderAgentCard($("#agent-slot"), b);
      renderResults($("#results"), b);
      if (live) toast(st === "completed" ? "Build finished. Results are below." : "The build stopped. The report explains why.", st === "completed" ? "ok" : "warn");
    } catch (e) {
      $("#results").innerHTML = `<div class="callout bad">${icon("warn")}<p>Couldn't load results: ${esc(e.message)}. Try refreshing the page.</p></div>`;
    }
  };

  stopStream = streamEvents(id, (ev) => {
    stepper.handle(ev);
    const d = describe(ev);
    if (d) {
      const li = document.createElement("li");
      li.className = d.kind || "";
      li.innerHTML = `<span class="ico">${icon(d.ico)}</span><div>${esc(d.text)}<time>${time(ev.ts)}</time></div>`;
      feed.appendChild(li);
      feed.scrollTop = feed.scrollHeight;
    }
    if (ev.type === "flags" && ev.kind === "groundability") $("#ground-slot").innerHTML = groundCards(ev.flags || []);
    if (ev.type === "stage_done" && ev.stage === "generate") showAgent();
    if (!live || finished) return;
    if (ev.type === "questions_asked" && ev.questions.length && !opts.non_interactive) {
      stepper.waitingForUser(1, "Waiting for your answers");
      const slot = $("#intake-slot");
      slot.innerHTML = "";
      slot.appendChild(intakeCard(id, ev.questions, () => stepper.set(1, { status: "running", note: "Writing requirements" })));
      slot.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (ev.type === "approval_requested") {
      const slot = $("#approval-slot");
      slot.innerHTML = "";
      slot.appendChild(approvalCard(id, ev.requirements, () => {}));
      slot.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    if (ev.type === "finished") finish(ev);
  }, (ev) => finish(ev));
}
