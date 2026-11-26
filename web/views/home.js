// Landing: hero, one-click demos, live stats band, what-it-does cards.
import { api } from "../api.js";
import { esc, icon, num, pct, term } from "../ui.js";
import { openHow } from "./how.js";

const DEMO_ICON = { hr: "people", spares: "ship", admissions: "cap" };

const heroArt = `<svg class="hero-art" viewBox="0 0 1200 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs><radialGradient id="sonar" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#5CC0FF" stop-opacity=".35"/><stop offset="1" stop-color="#5CC0FF" stop-opacity="0"/></radialGradient></defs>
  <g transform="translate(980 170)" fill="none" stroke="#7FB2FF">
    <circle r="60" stroke-opacity=".5"/><circle r="120" stroke-opacity=".35"/><circle r="190" stroke-opacity=".22"/><circle r="270" stroke-opacity=".12"/>
    <circle r="240" fill="url(#sonar)" stroke="none"/>
    <path d="M0 0 L250 -90" stroke="#5CC0FF" stroke-opacity=".6" stroke-width="2"/>
    <circle cx="120" cy="40" r="4" fill="#5CC0FF" stroke="none"/><circle cx="-80" cy="150" r="3" fill="#7FB2FF" stroke="none"/><circle cx="170" cy="-120" r="3" fill="#fff" stroke="none"/>
  </g>
  <g fill="none" stroke="#5CC0FF" stroke-width="1.5">
    <path d="M0 470 C150 440 300 500 450 470 S750 440 900 470 1050 500 1200 470" stroke-opacity=".35"/>
    <path d="M0 505 C150 475 300 535 450 505 S750 475 900 505 1050 535 1200 505" stroke-opacity=".22"/>
    <path d="M0 540 C150 510 300 570 450 540 S750 510 900 540 1050 570 1200 540" stroke-opacity=".12"/>
  </g></svg>`;

const FEATURES = [
  ["chat", "Interviewer", "Asks before it builds", "Up to five clarifying questions, never ones your brief or documents already answer."],
  ["shield", "Groundability guard", "Refuses instead of guessing", "Topics your documents can't support become refusals, flagged before a single prompt is written."],
  ["scale", "Hybrid judge", "Grades like a QA engineer", "Word-for-word fact checks first, then a separate LLM judge run twice in swapped order."],
  ["wand", "Optimizer", "Fixes one thing at a time", "Classifies every failure, applies one targeted fix, and reverts anything that makes it worse."],
];

export async function mount(root) {
  root.innerHTML = `
  <section class="hero" aria-labelledby="hero-title">
    ${heroArt}
    <div class="wrap">
      <span class="kicker"><span class="dot"></span>Brief in. Tested agent out.</span>
      <h1 id="hero-title">Describe. <span class="accent">Build.</span> Prove.</h1>
      <p class="hero-lede">Describe the assistant you need. ForgeAI builds, tests, and improves it, then tells you honestly what still fails.</p>
      <div class="row">
        <a class="btn btn-light" href="#/build">${icon("play")}Build an agent</a>
        <button class="btn btn-outline-light" type="button" id="how-open">How it works</button>
      </div>
      <h2 class="sr-only">Try a demo</h2>
      <p class="helper" style="color:#B9C8EE;margin-top:var(--s7)">Or try a demo: one click fills in a real brief and its documents.</p>
      <div class="grid grid-3 demo-cards" id="demo-cards" aria-live="polite">
        ${[1, 2, 3].map(() => '<div class="demo-card" aria-hidden="true"><div class="skel" style="height:44px;width:44px;background:rgba(255,255,255,.15)"></div><div class="skel" style="height:20px;background:rgba(255,255,255,.12)"></div><div class="skel" style="height:40px;background:rgba(255,255,255,.08)"></div></div>').join("")}
      </div>
    </div>
  </section>

  <section class="stats-band" aria-label="Live numbers from this server">
    <div class="wrap" id="stats">
      ${["Agents built", "Eval cases generated", "Average held-out score", "Issues fixed by the optimizer"].map((l) => `<div class="stat"><div class="value">…</div><div class="label">${l}</div></div>`).join("")}
    </div>
    <div class="wrap stats-note" id="stats-note">Live from this server's runs. Nothing on this band is made up.</div>
  </section>

  <section class="section" aria-labelledby="what-title">
    <div class="wrap">
      <div class="section-head">
        <span class="eyebrow">What ForgeAI does</span>
        <h2 id="what-title">The machine that builds the chatbot, then tests it like a QA engineer.</h2>
        <p>Every stage runs on a small, imperfect model, so every stage has a check that catches it lying.</p>
      </div>
      <div class="grid grid-4">
        ${FEATURES.map(([ic, name, sub, text]) => `<article class="card feature"><div class="badge-icon">${icon(ic)}</div><h3>${name}</h3><div class="sub">${sub}</div><p>${text}</p></article>`).join("")}
      </div>
      <div class="callout" style="margin-top:var(--s6)">${icon("info")}<p>New to this? The score you should trust is the ${term("held-out set", "held-out score")}: test questions the optimizer never saw. A ${term("hallucination")} or a ${term("retrieval miss")} is always named, never hidden. <a href="#/" id="how-link">See how it works</a>.</p></div>
    </div>
  </section>`;

  root.querySelector("#how-open").addEventListener("click", openHow);
  root.querySelector("#how-link").addEventListener("click", (e) => { e.preventDefault(); openHow(); });

  api.demos().then((demos) => {
    const box = root.querySelector("#demo-cards");
    if (!box) return;
    box.innerHTML = demos.map((d) => `
      <button class="demo-card" type="button" data-demo="${esc(d.id)}" aria-label="Try the ${esc(d.title)} demo">
        <div class="badge-icon">${icon(DEMO_ICON[d.id] || "doc")}</div>
        <strong>${esc(d.title)}</strong>
        <span class="sub">${esc(d.subtitle)}</span>
        <span class="small" style="color:#B9C8EE">${d.files.length} documents: ${d.files.map((f) => f.type.toUpperCase()).join(", ")}</span>
        <span class="link-arrow">Try it ${icon("arrow")}</span>
      </button>`).join("");
    box.querySelectorAll("[data-demo]").forEach((b) => b.addEventListener("click", () => { location.hash = `#/build?demo=${b.dataset.demo}`; }));
  }).catch((e) => { const box = root.querySelector("#demo-cards"); if (box) box.innerHTML = `<p class="helper" style="color:#fff">Demos unavailable: ${esc(e.message)}</p>`; });

  api.stats().then((s) => {
    const el = root.querySelector("#stats");
    if (!el) return;
    const vals = [num(s.agents_built), num(s.eval_cases), s.avg_heldout_score == null ? "–" : pct(s.avg_heldout_score), num(s.issues_fixed)];
    el.querySelectorAll(".value").forEach((v, i) => { v.textContent = vals[i]; });
    root.querySelector("#stats-note").textContent = s.agents_built
      ? `Live from ${s.agents_built} run${s.agents_built > 1 ? "s" : ""} on this server (average over ${s.runs_scored} completed). "Issues fixed" counts test cases that went from failing to passing after a kept optimizer change.`
      : "Live from this server. No agents built yet: start one and these numbers update.";
  }).catch(() => {});
}
