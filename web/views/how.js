// "How it works" modal: a simple flow diagram plus the glossary.
import { GLOSSARY, esc, icon, openModal } from "../ui.js";

const FLOW = [
  ["doc", "Your input", "A one-paragraph brief and a folder of documents (PDF, Word, Markdown, text, CSV).", true],
  ["chat", "1 Interview", "Up to 5 clarifying questions, then a requirements document."],
  ["shield", "2 Groundability", "Each topic checked against your documents. Gaps become refusals."],
  ["bot", "3 Generate", "System prompt, retrieval settings, only the tools it needs."],
  ["list", "4 Evals", "24+ test questions written from your documents, facts verified word-for-word."],
  ["scale", "5 Judge", "Deterministic checks plus an LLM judge that must pass a self-test."],
  ["wand", "6 Improve", "Diagnose failures, one targeted fix per round, revert if worse (max 3)."],
  ["chart", "7 Report", "Held-out score, what still fails and why, and every change logged."],
  ["play", "You get", "A runnable agent (agent.yaml), its test set and an honest report.", true],
];

export function openHow() {
  openModal(`
    <span class="eyebrow">How it works</span>
    <h2>From one paragraph to a tested agent</h2>
    <p class="muted">ForgeAI does what a careful GenAI engineer does by hand, and checks its own work at every step.</p>
    <div class="flow" role="list">
      ${FLOW.map(([ic, t, d, io]) => `<div class="node ${io ? "io" : ""}" role="listitem"><b>${icon(ic)}${esc(t)}</b><span>${esc(d)}</span></div>`).join("")}
    </div>
    <h3 style="margin-top:var(--s7)">Why you can trust the score</h3>
    <ul class="muted">
      <li>Expected answers are copied from your documents and checked character by character; numbers from spreadsheets are computed in code.</li>
      <li>The judge is a different model from the agent, never knows who wrote the answer, and grades twice with the order swapped.</li>
      <li>The quoted score comes from questions the optimizer never saw. Anything below target is labelled, never celebrated.</li>
    </ul>
    <h3 style="margin-top:var(--s6)">Glossary</h3>
    <dl class="glossary">${Object.entries(GLOSSARY).map(([k, v]) => `<div><dt>${esc(k[0].toUpperCase() + k.slice(1))}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>`, { label: "How ForgeAI works" });
}
