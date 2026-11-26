// Chat with any generated agent. Each reply has a "How I answered" panel.
import { api } from "../api.js";
import { emptyState, esc, icon, skeleton, term, toast } from "../ui.js";

const sessions = {}; // run_id -> [{role, html}] kept while the page is open

function starters(bundle) {
  const cases = ((bundle.evalset || {}).cases || []).filter((c) => !c.should_refuse && c.type !== "edge" && c.question.length < 120);
  const pick = cases.sort((a, b) => a.question.length - b.question.length).slice(0, 3).map((c) => c.question);
  const off = ((bundle.evalset || {}).cases || []).find((c) => c.should_refuse);
  if (off) pick.push(off.question);
  return pick;
}

function replyHtml(r, topics) {
  const conf = Math.round((r.confidence || 0) * 100);
  const rconf = Math.round((r.retrieval_confidence || 0) * 100);
  const tools = (r.tools_used || []).map((t) => `<li><span class="pill ${t.ok ? "ok" : "bad"}">${icon("tool")}${esc(t.tool)}</span> <span class="mono">${esc(JSON.stringify(t.args))}</span>${t.ok ? "" : ` <span class="muted">failed: ${esc(t.error || "")}</span>`}</li>`).join("");
  const body = r.refused
    ? `<div class="who">${icon("info")}Outside what I know</div><p style="margin:0">${esc(r.answer)}</p>${topics.length ? `<p class="small" style="margin:8px 0 0">I can help with: ${esc(topics.slice(0, 4).join("; "))}.</p>` : ""}`
    : `<div class="who">${icon("bot")}Agent</div>${esc(r.answer)}`;
  return `<div class="bubble bot ${r.refused ? "soft-refusal" : ""}">${body}
    <details class="how"><summary>How I answered</summary>
      <div class="small" style="margin-top:6px">
        ${r.refused ? `<span class="pill warn">refused</span> ${r.gate === "retrieval" ? `The ${term("refusal gate")} fired: nothing in the documents matched closely enough (${rconf}%).` : "The documents didn't contain an answer, so I declined instead of guessing."}` : ""}
        <div style="margin-top:6px"><strong>Sources:</strong> ${(r.sources || []).map((s) => `<span class="pill">${icon("doc")}${esc(s)}</span>`).join(" ") || "none"}</div>
        <div style="margin-top:6px"><strong>Confidence ${conf}%</strong><div class="meter ${conf >= 70 ? "ok" : conf >= 40 ? "warn" : "bad"}" role="meter" aria-valuenow="${conf}" aria-valuemin="0" aria-valuemax="100" aria-label="Answer confidence"><span style="width:${conf}%"></span></div>
          <span class="muted">Retrieval match ${rconf}% · passages: ${(r.retrieved || []).map((x) => esc(x.chunk_id)).join(", ") || "none"}</span></div>
        <div style="margin-top:6px"><strong>Tools used:</strong> ${tools ? `<ul style="margin:4px 0 0;padding-left:18px">${tools}</ul>` : "none"}</div>
      </div></details></div>`;
}

export async function mount(root, { param }) {
  root.innerHTML = `<div class="wrap"><div class="page-head"><span class="eyebrow">Chat</span><h1>Talk to a generated agent</h1>
    <p>Pick any agent ForgeAI built. Every reply shows its sources, confidence and tools, and it refuses politely when the documents don't cover a question.</p></div>
    <div id="chat-body">${skeleton(3)}</div></div>`;
  const runs = (await api.runs()).filter((r) => r.has_agent);
  const body = root.querySelector("#chat-body");
  if (!runs.length) {
    body.innerHTML = `<div class="card">${emptyState("chat", "No agents yet", "Build an agent first; it appears here as soon as generation finishes.", '<a class="btn btn-primary" href="#/build">Build an agent</a>')}</div>`;
    return;
  }
  let runId = runs.some((r) => r.run_id === param) ? param : runs[0].run_id;
  body.innerHTML = `<div class="chat-shell">
    <aside class="card stack" aria-label="Agent">
      <div><label class="field" for="agent-select">Agent</label>
        <select class="input" id="agent-select">${runs.map((r) => `<option value="${esc(r.run_id)}">${esc(r.title || r.run_id)} · ${esc(r.run_id)}</option>`).join("")}</select>
        <span class="helper">Each agent answers only from the documents it was built with.</span></div>
      <div id="agent-info">${skeleton(1)}</div>
    </aside>
    <section class="card" style="padding:0" aria-label="Conversation">
      <div class="chat-log" id="chat-log" aria-live="polite"></div>
      <div style="padding:0 var(--s4)"><div class="chips" id="starters" aria-label="Suggested questions"></div></div>
      <form class="composer" id="composer">
        <label class="sr-only" for="chat-input">Your question</label>
        <input class="input" id="chat-input" autocomplete="off" placeholder="Ask a question…" maxlength="1000">
        <button class="btn btn-primary" type="submit" aria-label="Send">${icon("arrow")}<span class="hide-sm">Send</span></button>
      </form>
    </section></div>`;
  const sel = body.querySelector("#agent-select"), log = body.querySelector("#chat-log"), input = body.querySelector("#chat-input");
  let topics = [];

  const paintLog = () => {
    const s = sessions[runId] || [];
    log.innerHTML = s.length ? s.map((m) => m.html).join("") : `<div class="empty" style="padding:var(--s6)">${icon("chat")}<h3>Ask your first question</h3><p>Try one of the suggestions below. Each was generated from this agent's own test set.</p></div>`;
    log.scrollTop = log.scrollHeight;
  };
  const load = async () => {
    sel.value = runId;
    history.replaceState(null, "", `#/chat/${encodeURIComponent(runId)}`);
    paintLog();
    try {
      const b = await api.bundle(runId);
      const a = b.agent || {}, req = b.requirements || {};
      topics = req.must_answer || [];
      body.querySelector("#agent-info").innerHTML = `<div class="badge-icon">${icon("bot")}</div>
        <h3 style="margin-top:10px">${esc(req.title || a.name)}</h3><p class="small muted">${esc(req.scope || a.description || "")}</p>
        <div class="small"><strong>Answers:</strong> ${esc(topics.join("; ") || "–")}</div>
        <div class="small" style="margin-top:6px"><strong>Refuses:</strong> ${esc((a.must_refuse || []).join("; ") || "–")}</div>
        <div class="chips" style="margin-top:8px">${(a.tools || []).map((t) => `<span class="pill ok">${icon("tool")}${esc(t)}</span>`).join("") || '<span class="pill">no tools</span>'}</div>`;
      body.querySelector("#starters").innerHTML = starters(b).map((q) => `<button class="chip" type="button" title="${esc(q)}" data-q="${esc(q)}">${esc(q.length > 70 ? q.slice(0, 67) + "…" : q)}</button>`).join("");
      body.querySelectorAll("[data-q]").forEach((c) => c.addEventListener("click", () => ask(c.dataset.q)));
    } catch (e) { toast(e.message, "bad"); }
  };
  const ask = async (q) => {
    q = q.trim();
    if (!q) return;
    const s = (sessions[runId] ||= []);
    s.push({ html: `<div class="bubble user"><div class="who">${icon("user")}You</div>${esc(q)}</div>` });
    paintLog();
    log.insertAdjacentHTML("beforeend", `<div class="bubble bot" id="typing" aria-label="Agent is typing"><span class="typing"><i></i><i></i><i></i></span></div>`);
    log.scrollTop = log.scrollHeight;
    input.value = "";
    try {
      const r = await api.chat(runId, q);
      s.push({ html: replyHtml(r, topics) });
    } catch (e) {
      s.push({ html: `<div class="bubble bot soft-refusal"><div class="who">${icon("warn")}Couldn't reach the agent</div>${esc(e.message)} Try again in a moment.</div>` });
    }
    paintLog();
    input.focus();
  };
  sel.addEventListener("change", () => { runId = sel.value; load(); });
  body.querySelector("#composer").addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
  load();
}
