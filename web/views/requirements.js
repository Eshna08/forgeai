// The assignment's 9 requirements + stretch goals, each checked live against real run artifacts.
import { api } from "../api.js";
import { esc, icon, skeleton } from "../ui.js";

const WHAT = {
  R1: "Reads the brief and documents, asks at most 5 questions, writes scope / audience / tone / must-answer / must-refuse.",
  R2: "Topics the documents can't support are flagged and moved to must-refuse, never hallucinated.",
  R3: "Declarative agent.yaml: prompt, retrieval settings, only the tools the brief needs, output contract.",
  R4: "24+ test questions generated from the documents: answerable, out-of-scope and edge cases, facts verified.",
  R5: "Deterministic checks plus an LLM judge defended against position, verbosity and self-preference bias.",
  R6: "Classify every failure, one targeted fix per round, revert on regression, max 3 rounds, full log.",
  R7: "Report with per-iteration scorecard, what still fails and why, and the limits of the evaluation.",
  R8: "A generic chat runner loads any agent.yaml: CLI, web and POST /api/chat.",
  R9: "Full artifacts of the HR, ship-spares and admissions demos committed under runs/.",
  S1: "Three prompt strategies; the dev set picks the winner; held-out score reported separately.",
  S2: "Token and wall-clock caps with early stop.",
  S3: "Approve / edit / reject the requirements before anything is generated.",
  S4: "Re-run an old test set on changed documents and classify what broke.",
  S5: "The seed is stored in every run's metadata.",
};
const ST = { pass: ["check", "Pass"], partial: ["warn", "Partial"], fail: ["x", "Fail"] };

export async function mount(root) {
  root.innerHTML = `<div class="wrap"><div class="page-head"><span class="eyebrow">Requirements</span><h1>Assignment checklist, verified live</h1>
    <p>Each item is checked right now against the artifacts on this server, not a static list. Open the evidence to see the file itself.</p>
    <div class="row"><span class="small muted" id="req-run"></span><button class="btn btn-ghost btn-sm" type="button" id="req-refresh">${icon("refresh")}Re-check</button></div></div>
    <div id="req-body">${skeleton(4)}</div></div>`;
  const load = async () => {
    const body = root.querySelector("#req-body");
    body.innerHTML = skeleton(4);
    try {
      const r = await api.requirementsStatus();
      root.querySelector("#req-run").textContent = r.run_id ? `Checked against the latest completed run: ${r.run_id}` : "No completed run yet: build an agent to turn these green.";
      const group = (g, title, sub) => {
        const items = r.items.filter((i) => i.group === g);
        const passed = items.filter((i) => i.status === "pass").length;
        return `<section class="section" style="padding-top:0" aria-labelledby="g-${g}"><div class="row" style="margin-bottom:12px"><h2 id="g-${g}">${title}</h2><span class="pill ${passed === items.length ? "ok" : "warn"}">${passed}/${items.length} passing</span></div>
          <p class="muted">${sub}</p>
          <div class="grid grid-2" style="gap:12px">${items.map((i) => {
            const [ic, label] = ST[i.status] || ST.fail;
            return `<article class="card card-tight req" data-req="${esc(i.id)}">
              <div class="st ${esc(i.status)}" aria-hidden="true">${icon(ic)}</div>
              <div style="min-width:0"><div class="row"><h3>${esc(i.id)} · ${esc(i.title)}</h3><span class="pill ${i.status === "pass" ? "ok" : i.status === "partial" ? "warn" : "bad"}">${label}</span></div>
                <p class="small muted" style="margin:4px 0">${esc(WHAT[i.id] || "")}</p>
                <p class="small" style="margin:4px 0"><strong>Live check:</strong> ${esc(i.detail)}</p>
                <p class="small" style="margin:4px 0"><strong>See it in the UI:</strong> ${esc(i.ui)}</p>
                <div class="chips">${i.evidence.map((e) => `<a class="pill info" href="${esc(e.url)}" target="_blank" rel="noopener">${icon("doc")}${esc(e.label)}</a>`).join("")}</div>
              </div></article>`;
          }).join("")}</div></section>`;
      };
      body.innerHTML = group("core", "The 9 mandatory requirements", "All nine are required by the assignment.") + group("stretch", "Stretch goals", "Optional extras for bonus credit. 'Partial' means available in the product but not exercised by a run on this server yet.");
    } catch (e) {
      body.innerHTML = `<div class="callout bad">${icon("warn")}<p>${esc(e.message)}</p></div>`;
    }
  };
  root.querySelector("#req-refresh").addEventListener("click", load);
  load();
}
