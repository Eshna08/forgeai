// Agent definition card + results dashboard (score, charts, what still fails, changelog, tournament, cases).
import { api } from "../api.js";
import { enableChartTips, legend, lineChart, stackedBars } from "../charts.js";
import { CATEGORY, esc, icon, num, pct, ring, scoreColor, term } from "../ui.js";

const titleCase = (s) => (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export function renderAgentCard(el, b) {
  const a = b.agent, t = b.tools || {}, req = b.requirements || {}, cal = t.calibration || {};
  el.innerHTML = `<article class="card" aria-labelledby="agent-title">
    <div class="card-head"><div class="badge-icon">${icon("bot")}</div><div>
      <h3 id="agent-title">${esc(req.title || titleCase(a.name))}</h3>
      <p>${esc(req.audience ? `For ${req.audience}` : a.description)}</p></div></div>
    <dl class="stack" style="margin:0">
      <div><dt class="small muted">Purpose</dt><dd style="margin:0">${esc(req.scope || a.description)}</dd></div>
      <div><dt class="small muted">Tone</dt><dd style="margin:0">${esc(req.tone || "–")}</dd></div>
      <div><dt class="small muted">Will refuse</dt><dd style="margin:4px 0 0"><div class="chips">${(a.must_refuse || []).map((x) => `<span class="pill bad">${esc(x)}</span>`).join("") || "–"}</div></dd></div>
      <div><dt class="small muted">Tools attached</dt><dd style="margin:4px 0 0">${(t.attached || []).length
        ? (t.attached || []).map((x) => `<div class="row small" style="margin-bottom:4px"><span class="pill ok">${icon("tool")}${esc(x.name)}</span><span class="muted">${esc(x.rule || x.justification)}</span></div>`).join("")
        : '<span class="small muted">None. This agent answers only from its documents.</span>'}</dd></div>
      <div><dt class="small muted">Tools rejected (and why)</dt><dd style="margin:4px 0 0">${(t.rejected || []).map((x) => `<div class="row small" style="margin-bottom:4px"><span class="pill">${esc(x.name)}</span><span class="muted">${esc(x.reason)}</span></div>`).join("") || '<span class="small muted">None</span>'}</dd></div>
      <div><dt class="small muted">${term("retrieval", "Retrieval")} settings</dt><dd style="margin:4px 0 0"><div class="chips">
        <span class="pill">chunks ${a.chunk_size} chars</span><span class="pill">overlap ${a.chunk_overlap}</span><span class="pill">top ${a.top_k} passages</span>
        <span class="pill">${Math.round(a.hybrid_weight * 100)}% embeddings / ${100 - Math.round(a.hybrid_weight * 100)}% keywords</span>
        <span class="pill info">${term("refusal gate")} at ${Math.round(a.refusal_threshold * 100)}%</span></div>
        ${cal.threshold ? `<span class="helper">Threshold calibrated between off-topic probes (${Math.round(cal.off_topic_p90 * 100)}%) and in-domain probes (${Math.round(cal.in_domain_p10 * 100)}%) using ${esc(cal.embedder)} embeddings.</span>` : ""}</dd></div>
    </dl>
    <details style="margin-top:14px"><summary class="small" style="cursor:pointer;font-weight:600">Show raw agent.yaml</summary><pre class="diff">${esc(b.agent_yaml)}</pre></details>
  </article>`;
}

export function likelyReason(r) {
  const det = (r.judge || {}).deterministic || {};
  switch (r.category) {
    case "retrieval_miss": return `The passage with the answer wasn't retrieved (got ${(r.retrieved || []).slice(0, 2).join(", ") || "nothing"}).`;
    case "wrong_refusal": return r.gate === "retrieval" ? `Refusal gate fired: retrieval confidence ${Math.round((r.retrieval_confidence || 0) * 100)}% was below the threshold.` : "The model refused although the evidence was retrieved.";
    case "hallucination": return r.should_refuse ? "Answered a question it should have refused." : `Answer contains claims not in the documents: ${(det.unsupported || []).join(", ")}.`;
    default: {
      if ((r.judge || {}).decided_by === "llm_veto") return "Word-level checks passed, but both judge orderings said the answer was wrong or ungrounded.";
      const miss = (r.expected_key_facts || []).filter((f) => !(det.facts_found || []).includes(f));
      return `Evidence was retrieved but the answer missed: ${miss.join(", ") || "expected facts"}.`;
    }
  }
}

const catPill = (c) => (c ? `<span class="pill" style="color:${CATEGORY[c]?.color};border-color:currentColor;background:transparent">${CATEGORY[c]?.label || c}</span>` : "");

function diffHtml(d) {
  return esc(d).split("\n").map((l) => `<span class="${l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : l.startsWith("@@") ? "hunk" : ""}">${l || " "}</span>`).join("");
}

export function renderResults(el, b) {
  const meta = b.meta || {}, sc = b.scorecard || {}, target = b.target ?? 90;
  const its = (b.iterations || {}).iterations || [];
  const results = (b.results || {}).results || [];
  const held = results.filter((r) => r.split === "heldout"), dev = results.filter((r) => r.split === "dev");
  const heldScore = sc.heldout_score ?? meta.heldout_score, devScore = sc.dev_score ?? meta.dev_score;
  const fails = results.filter((r) => !r.passed);
  const stats = (b.evalset || {}).stats || {};
  const failed = meta.status && meta.status !== "completed";

  if (heldScore == null) {
    el.innerHTML = `<div class="card"><div class="callout ${meta.status === "rejected" ? "warn" : "bad"}">${icon("warn")}<div>
      <p><strong>${meta.status === "rejected" ? "You rejected the requirements, so nothing was built." : "This run stopped before it could be scored."}</strong></p>
      <p>${esc(meta.error ? `Stage "${meta.error.stage}": ${meta.error.message}` : "See the report for details.")}</p>
      <p>Next step: fix the cause above (documents, brief, or budget in .env) and start a new build.</p></div></div>
      <div class="row" style="margin-top:14px"><a class="btn btn-secondary" href="${api.artifactUrl(b.run_id, "report.md")}" target="_blank" rel="noopener">${icon("doc")}Read the partial report</a>
      <a class="btn btn-primary" href="#/build">Start a new build</a></div></div>`;
    return;
  }

  const meets = heldScore >= target;
  const verdict = meets
    ? `Meets the target of ${target}% on ${held.length} held-out questions.`
    : `Below the target of ${target}%. ${fails.filter((r) => r.split === "heldout").length} of ${held.length} held-out questions still fail; each one is explained below.`;
  const baseline = its[0]?.score_after;
  const points = its.filter((i) => i.score_after != null).map((i) => ({ label: i.iteration === 0 ? "baseline" : `iter ${i.iteration}`, value: i.score_after, kind: i.iteration === 0 ? "baseline" : i.decision?.startsWith("reverted") ? "reverted" : "kept" }));
  const bars = its.filter((i) => i.score_after != null).map((i) => ({ label: i.iteration === 0 ? "baseline" : `iter ${i.iteration}`, counts: i.iteration === 0 ? i.taxonomy : i.taxonomy_after }));
  bars.push({ label: "held-out", counts: Object.fromEntries(Object.keys(CATEGORY).map((c) => [c, held.filter((r) => r.category === c).length])) });
  const fixes = its.filter((i) => i.kind === "fix" || i.kind === "aborted");
  const t = b.tournament;
  const usage = meta.usage || {};

  el.innerHTML = `
  <div class="stack">
    <span class="eyebrow">Results</span>
    <section class="card" aria-labelledby="score-title">
      <div class="score-hero">
        <div class="score-ring">${ring(heldScore, 160, 12, scoreColor(heldScore, target))}<div class="val"><div><strong>${pct(heldScore)}</strong><small>held-out score</small></div></div></div>
        <div>
          <h2 id="score-title">${meets ? "Meets target" : "Below target"}<span class="sr-only">: ${pct(heldScore)} held-out</span></h2>
          <p>${esc(verdict)} This is the number to quote: the optimizer never saw these questions (${term("held-out set")}).</p>
          <div class="kpis">
            <div class="kpi"><b>${pct(devScore)}</b><span>${term("dev set", "dev score")} (optimistic)</span></div>
            <div class="kpi"><b>${pct(baseline)}</b><span>baseline before fixes</span></div>
            <div class="kpi"><b>${num(stats.total)}</b><span>${term("eval set", "test questions")}</span></div>
            <div class="kpi"><b>${fixes.length}</b><span>optimizer iterations</span></div>
          </div>
          <p class="small muted" style="margin-top:10px">Stopped because: ${esc((b.iterations || {}).stop_reason || meta.stop_reason || "–")}</p>
        </div>
      </div>
      ${meta.provider === "mock" ? `<div class="callout" style="margin-top:14px">${icon("info")}<p>Built with the offline mock model. These numbers prove the factory's mechanics, not a real model's quality. Add an API key in <code>.env</code> for real results.</p></div>` : ""}
      ${heldScore >= 100 ? `<div class="callout warn" style="margin-top:10px">${icon("warn")}<p><strong>100% is not a claim that the agent is correct.</strong> It means every one of ${held.length} synthetic held-out questions passed. Not tested: multi-turn chat, prompt injection, non-English questions, real user phrasing.</p></div>` : ""}
      ${failed ? `<div class="callout bad" style="margin-top:10px">${icon("warn")}<p>Run status: ${esc(meta.status)}. Some stages did not finish; see the report.</p></div>` : ""}
    </section>

    <section class="card" aria-labelledby="fails-title" style="border-color:${fails.length ? "var(--warning)" : "var(--border-soft)"}">
      <div class="card-head"><div class="badge-icon" style="background:var(--warning-soft);color:var(--warning)">${icon("search")}</div><div>
        <h3 id="fails-title">What still fails and why</h3><p>Every failing test question, its failure category, and the most likely reason. Nothing is hidden.</p></div></div>
      ${fails.length ? `<div class="table-wrap"><table class="t"><thead><tr><th scope="col">Case</th><th scope="col">Question</th><th scope="col">Category</th><th scope="col">Likely reason</th></tr></thead><tbody>
        ${fails.map((r) => `<tr><td class="mono">${esc(r.case_id)}<br><span class="small muted">${r.split}</span></td><td>${esc(r.question)}</td><td>${catPill(r.category)}</td><td>${esc(likelyReason(r))}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="callout ok">${icon("check")}<p>No test question fails in the dev or held-out set. That doesn't make the agent flawless: the set is small and synthetic. See the limits in the report.</p></div>`}
    </section>

    <div class="grid grid-2">
      <section class="card" aria-labelledby="chart1">
        <h3 id="chart1">${icon("chart")}Score per iteration</h3>
        <p class="small muted">Dev-set score after each optimizer change. The dashed line is the target (${target}%). Red points were reverted because the score dropped; the square is the held-out score.</p>
        ${lineChart({ points, target, heldout: heldScore })}
        ${points.length <= 1 ? `<p class="small muted">No improvement rounds were needed or possible: ${esc((b.iterations || {}).stop_reason || "")}.</p>` : ""}
      </section>
      <section class="card" aria-labelledby="chart2">
        <h3 id="chart2">${icon("list")}Why tests failed</h3>
        <p class="small muted">Failures per round by category: ${term("retrieval miss")}, ${term("prompt defect")}, ${term("hallucination")}, ${term("wrong refusal")}.</p>
        ${stackedBars(bars)}${legend()}
      </section>
    </div>

    <section class="card" aria-labelledby="log-title">
      <div class="card-head"><div class="badge-icon">${icon("wand")}</div><div><h3 id="log-title">Optimizer changelog</h3>
        <p>One targeted fix per round, never a full rewrite. Changes that lowered the score were reverted.</p></div></div>
      <ol class="timeline">
        <li><span class="tl-year">Baseline</span><div class="card card-tight"><strong>${pct(baseline)}</strong> on the dev set${t ? ` with the tournament winner (${esc(t.winner)})` : ""}.
          ${its[0]?.taxonomy && Object.keys(its[0].taxonomy).length ? `<div class="chips" style="margin-top:6px">${Object.entries(its[0].taxonomy).map(([k, v]) => `${catPill(k)}<span class="small">×${v}</span>`).join(" ")}</div>` : ""}</div></li>
        ${fixes.map((i) => `<li class="${i.decision?.startsWith("reverted") ? "reverted" : ""}"><span class="tl-year">Iteration ${i.iteration}</span>
          <div class="card card-tight">
            <div class="row">${catPill(i.category)}<strong>${esc(i.change || i.reason || "")}</strong><span class="spacer"></span>
              ${i.kind === "aborted" ? '<span class="pill bad">aborted</span>' : i.decision?.startsWith("reverted") ? '<span class="pill bad">reverted</span>' : '<span class="pill ok">kept</span>'}</div>
            ${i.why ? `<p class="small" style="margin-top:6px"><strong>Why:</strong> ${esc(i.why)}</p>` : ""}
            ${i.score_after != null ? `<p class="small"><strong>Score:</strong> ${pct(i.score_before)} → ${pct(i.score_after)} · fixed ${(i.fixed_ids || []).length} · newly passing ${(i.newly_passing_ids || []).length} · regressions ${(i.regression_ids || []).length} · ${num(i.tokens)} tokens · ${i.latency_s}s</p>` : ""}
            ${i.diff ? `<details><summary class="small" style="cursor:pointer;font-weight:600">Show the change (diff)</summary><pre class="diff">${diffHtml(i.diff)}</pre></details>` : ""}
          </div></li>`).join("")}
        <li><span class="tl-year">Stop</span><div class="card card-tight small">${esc((b.iterations || {}).stop_reason || "–")}</div></li>
      </ol>
    </section>

    ${t ? `<section class="card" aria-labelledby="tour-title">
      <div class="card-head"><div class="badge-icon">${icon("scale")}</div><div><h3 id="tour-title">Prompt tournament</h3><p>${esc(t.rule)}.</p></div></div>
      <div class="table-wrap"><table class="t"><thead><tr><th scope="col">Strategy</th><th scope="col">Dev score</th><th scope="col">Hallucinations</th><th scope="col">Tokens</th><th scope="col">Held-out</th></tr></thead><tbody>
      ${t.candidates.map((c) => `<tr class="${c.strategy === t.winner ? "winner" : ""}"><td>${esc(titleCase(c.strategy))}${c.strategy === t.winner ? ' <span class="pill ok">winner</span>' : ""}</td><td>${pct(c.score)}</td><td>${c.hallucinations}</td><td>${num(c.tokens)}</td><td>${c.strategy === t.winner ? pct(heldScore) : '<span class="muted small">not run</span>'}</td></tr>`).join("")}
      </tbody></table></div><p class="small muted" style="margin-top:8px">Held-out is measured only for the shipped agent, after the choice was made, so the held-out questions never influence the winner.</p></section>` : ""}

    <section class="card" aria-labelledby="cases-title">
      <div class="card-head"><div class="badge-icon">${icon("list")}</div><div><h3 id="cases-title">Every test question</h3>
        <p>${num(stats.total)} questions written from your documents (${Object.entries(stats.by_type || {}).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ")}). Open a row to see the expected facts, the agent's answer and the judge's reasoning.</p></div></div>
      <div class="chips" role="group" aria-label="Filter test questions" id="case-filters">
        ${[["all", "All"], ["fail", "Failing"], ["answerable", "Answerable"], ["out_of_scope", "Out of scope"], ["edge", "Edge cases"], ["heldout", "Held-out only"]].map(([k, l], i) => `<button class="chip" type="button" data-f="${k}" aria-pressed="${i === 0}">${l}</button>`).join("")}
      </div>
      <div class="cases" id="cases" style="margin-top:12px"></div>
    </section>

    <div class="grid grid-3">
      <section class="card" aria-labelledby="judge-title"><h3 id="judge-title">${icon("scale")}${term("judge self-test", "Judge self-test")}</h3>
        ${b.selftest ? `<p><strong>${b.selftest.n_correct}/${b.selftest.n}</strong> planted answers graded correctly.</p><ul class="small" style="padding-left:18px;margin:0">${b.selftest.cases.map((c) => `<li>${c.caught ? "✓" : "✗"} ${esc(c.case)}</li>`).join("")}</ul>` : '<p class="muted">Not run.</p>'}</section>
      <section class="card" aria-labelledby="budget-title"><h3 id="budget-title">${icon("clock")}Budget</h3>
        <p class="small">Tokens ${num(usage.tokens)} of ${num(usage.max_tokens)}</p><div class="meter"><span style="width:${Math.min(100, ((usage.tokens || 0) / (usage.max_tokens || 1)) * 100)}%"></span></div>
        <p class="small" style="margin-top:8px">Time ${usage.elapsed_s ?? "–"}s of ${usage.max_seconds ?? "–"}s · ${num(usage.calls)} LLM calls · ${num(usage.fallbacks)} fallbacks</p></section>
      <section class="card" aria-labelledby="dl-title"><h3 id="dl-title">${icon("download")}Take it with you</h3>
        <div class="stack">
          <a class="btn btn-primary btn-sm" href="#/chat/${encodeURIComponent(b.run_id)}">${icon("chat")}Chat with this agent</a>
          <a class="btn btn-secondary btn-sm" href="${api.artifactUrl(b.run_id, "report.md")}" target="_blank" rel="noopener">${icon("doc")}Open report.md</a>
          <a class="btn btn-secondary btn-sm" href="${api.zipUrl(b.run_id)}">${icon("download")}Download all artifacts (.zip)</a>
        </div></section>
    </div>
  </div>`;

  enableChartTips(el);
  const box = el.querySelector("#cases");
  const facts = Object.fromEntries(((b.evalset || {}).cases || []).map((c) => [c.id, c]));
  const paint = (f) => {
    const rows = results.filter((r) => f === "all" || (f === "fail" && !r.passed) || (f === "heldout" && r.split === "heldout") || r.type === f);
    box.innerHTML = rows.length ? rows.map((r) => {
      const j = r.judge || {}, det = j.deterministic || {}, llm = j.llm;
      const c = facts[r.case_id] || {};
      return `<details class="case"><summary><span class="mono small">${esc(r.case_id)}</span><span class="q">${esc(r.question)}</span>
        <span class="row" style="gap:6px">${r.passed ? '<span class="pill ok">pass</span>' : `<span class="pill bad">fail</span>${catPill(r.category)}`}</span></summary>
        <dl class="body">
          <div><dt>Type</dt><dd>${esc(titleCase(r.type))} · ${esc(r.subtype)} · ${r.split}${r.should_refuse ? " · should refuse" : ""}</dd></div>
          <div><dt>Expected facts</dt><dd>${(r.expected_key_facts || []).map((x) => `<span class="pill">${esc(x)}</span>`).join(" ") || (r.should_refuse ? "A polite refusal" : "–")} ${c.expected_source_docs?.length ? `<span class="small muted">from ${esc(c.expected_source_docs.join(", "))}</span>` : ""}</dd></div>
          <div><dt>Agent answer</dt><dd>${r.refused ? '<span class="pill warn">refused</span> ' : ""}${esc(r.answer)}<br><span class="small muted">sources: ${esc((r.sources || []).join(", ") || "none")} · confidence ${Math.round((r.confidence || 0) * 100)}%${r.tools_used?.length ? ` · tools: ${esc(r.tools_used.map((x) => x.tool).join(", "))}` : ""}</span></dd></div>
          <div><dt>Judge reasoning</dt><dd>Decided by <strong>${esc((j.decided_by || "").replace(/_/g, " "))}</strong>. ${det.fact_coverage != null ? `Fact coverage ${Math.round(det.fact_coverage * 100)}%. ` : ""}${det.unsupported?.length ? `Unsupported terms: ${esc(det.unsupported.join(", "))}. ` : ""}${llm ? `LLM judge (two orderings): ${esc(llm.status)}${llm.order_a?.reason ? ` — "${esc(llm.order_a.reason)}"` : ""}.` : r.should_refuse || r.refused ? "Refusal cases are graded deterministically." : ""}
            ${!r.passed ? `<br><strong>Likely reason:</strong> ${esc(likelyReason(r))}` : ""}</dd></div>
        </dl></details>`;
    }).join("") : '<p class="muted">No questions match this filter.</p>';
  };
  el.querySelectorAll("#case-filters .chip").forEach((btn) => btn.addEventListener("click", () => {
    el.querySelectorAll("#case-filters .chip").forEach((x) => x.setAttribute("aria-pressed", String(x === btn)));
    paint(btn.dataset.f);
  }));
  paint("all");
}
