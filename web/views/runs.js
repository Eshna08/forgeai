// Past runs as cards + regression mode (re-run an old test set against changed documents).
import { api } from "../api.js";
import { emptyState, esc, icon, pct, ring, scoreColor, skeleton, toast, when } from "../ui.js";

const REG = [["still_passing", "Still passing", "ok"], ["regression", "Regressions", "bad"], ["newly_passing", "Newly passing", "ok"],
  ["still_failing", "Still failing", "warn"], ["stale_eval", "Stale tests", "warn"]];

export async function mount(root) {
  root.innerHTML = `<div class="wrap"><div class="page-head"><span class="eyebrow">Runs</span><h1>Every agent ForgeAI built</h1>
    <p>Open a run to see its report, chat with its agent, or download every artifact. Scores are held-out scores.</p></div>
    <div id="runs-grid" class="grid grid-3">${skeleton(1)}${skeleton(1)}${skeleton(1)}</div>
    <section class="card" style="margin:var(--s7) 0 var(--s9)" aria-labelledby="reg-title">
      <div class="card-head"><div class="badge-icon">${icon("refresh")}</div><div><h3 id="reg-title">Regression check</h3>
        <p>Documents changed? Re-run a run's old test questions against the new documents and see what broke, what improved, and which tests are now stale.</p></div></div>
      <form id="reg-form" class="grid grid-2" style="gap:12px">
        <div><label class="field" for="reg-run">Run to check</label><select class="input" id="reg-run"></select></div>
        <div><label class="field" for="reg-files">Changed documents</label><input class="input" id="reg-files" type="file" multiple accept=".txt,.md,.pdf,.docx,.csv">
          <label class="toggle-card" style="margin-top:8px"><input type="checkbox" id="reg-sample"><div><strong>Use the sample changed HR documents</strong><span>Leave 25→28 days, hotel cap 180→200, study leave removed. Pair it with an HR run.</span></div></label></div>
        <div><button class="btn btn-primary" type="submit">${icon("play")}Run regression check</button><span class="helper">Uses the run's original agent settings and test set; only the documents change.</span></div>
      </form>
      <div id="reg-out" aria-live="polite" style="margin-top:14px"></div>
    </section></div>`;

  let runs = [];
  try { runs = await api.runs(); } catch (e) { toast(e.message, "bad"); }
  const grid = root.querySelector("#runs-grid");
  if (!runs.length) {
    grid.outerHTML = `<div class="card">${emptyState("list", "No runs yet", "Build your first agent; it shows up here with its score and artifacts.", '<a class="btn btn-primary" href="#/build">Build an agent</a>')}</div>`;
  } else {
    grid.innerHTML = runs.map((r) => {
      const s = r.heldout_score;
      const st = r.status === "completed" ? "ok" : r.status === "running" ? "info" : r.status === "rejected" ? "warn" : "bad";
      return `<article class="card run-card">
        <div class="top"><div class="mini-ring">${ring(s ?? 0, 64, 7, scoreColor(s, 90))}<b>${s == null ? "–" : Math.round(s)}</b></div>
          <div style="min-width:0"><h3>${esc(r.title || r.run_id)}</h3><span class="small muted">${esc(when(r.started_at))}</span></div></div>
        <p class="brief">${esc(r.brief)}</p>
        <div class="chips"><span class="pill ${st}">${esc(r.status)}</span>${r.provider ? `<span class="pill">${esc(r.provider)}</span>` : ""}${(r.tags || []).slice(0, 4).map((t) => `<span class="pill">${esc(t.length > 28 ? t.slice(0, 26) + "…" : t)}</span>`).join("")}</div>
        <p class="small muted" style="margin:0">Held-out ${pct(s)} · dev ${pct(r.dev_score)}${r.stop_reason ? ` · ${esc(r.stop_reason)}` : ""}</p>
        <div class="row" style="margin-top:auto">
          <a class="btn btn-primary btn-sm" href="#/run/${encodeURIComponent(r.run_id)}" aria-label="Open run ${esc(r.run_id)}">Open</a>
          ${r.has_agent ? `<a class="btn btn-secondary btn-sm" href="#/chat/${encodeURIComponent(r.run_id)}">${icon("chat")}Chat</a>` : ""}
          <a class="btn btn-ghost btn-sm" href="${api.zipUrl(r.run_id)}" aria-label="Download artifacts of ${esc(r.run_id)}">${icon("download")}.zip</a>
        </div></article>`;
    }).join("");
  }

  const sel = root.querySelector("#reg-run");
  const done = runs.filter((r) => r.status === "completed");
  sel.innerHTML = done.length ? done.map((r) => `<option value="${esc(r.run_id)}">${esc(r.title || r.run_id)} · ${esc(r.run_id)}</option>`).join("") : '<option value="">No completed runs yet</option>';
  root.querySelector("#reg-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const out = root.querySelector("#reg-out");
    const files = root.querySelector("#reg-files").files;
    const sample = root.querySelector("#reg-sample").checked;
    if (!sel.value) { toast("Build and finish a run first.", "warn"); return; }
    if (!files.length && !sample) { toast("Choose the changed documents, or tick the sample option.", "warn"); return; }
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    fd.append("demo_v2", String(sample));
    out.innerHTML = skeleton(2);
    try {
      const r = await api.regress(sel.value, fd);
      out.innerHTML = `<p><strong>Old test set on the new documents: ${pct(r.score_now)}</strong> (stale tests count as failures in this number).</p>
        <div class="kpis">${REG.map(([k, l, c]) => `<div class="kpi"><b style="color:var(--${c === "ok" ? "success" : c === "bad" ? "danger" : "warning"})">${r.summary[k] ?? 0}</b><span>${l}</span></div>`).join("")}</div>
        <p class="small muted" style="margin-top:10px">Stale tests expect facts that no longer exist in the documents: regenerate the test set rather than blaming the agent.</p>
        <a class="link-arrow" href="${api.artifactUrl(sel.value, "regression_report.md")}" target="_blank" rel="noopener">Open the regression report ${icon("arrow")}</a>`;
      toast("Regression check finished.", "ok");
    } catch (err) { out.innerHTML = `<div class="callout bad">${icon("warn")}<p>${esc(err.message)}</p></div>`; }
  });
}
