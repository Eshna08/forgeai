// Shared UI helpers: escaping, icons, toasts, modal, glossary terms, small formatters.

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const P = {
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  warn: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  doc: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
  tool: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  chart: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
  people: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  cap: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
  ship: '<path d="M2 21c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1 .6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M19.4 18 21 12l-9-4-9 4 1.6 6M12 8V2M8 5h8"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  play: '<path d="m6 3 14 9-14 9z"/>',
  refresh: '<path d="M21 2v6h-6M3 22v-6h6"/><path d="M20.5 9A9 9 0 0 0 5.6 5.6L3 8M21 16l-2.6 2.4A9 9 0 0 1 3.5 15"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  bot: '<rect x="3" y="8" width="18" height="12" rx="3"/><path d="M12 8V4M8 14h.01M16 14h.01M9 18h6"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  compass: '<circle cx="12" cy="12" r="10"/><path d="m16.2 7.8-2.1 6.3-6.3 2.1 2.1-6.3z"/>',
  flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  wand: '<path d="m15 4-11 11 3 3 11-11zM14 7l3 3M5 3v4M3 5h4M19 13v4M17 15h4"/>',
  scale: '<path d="M12 3v18M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0zM8 21h8"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3"/>',
};

export function icon(name, cls = "") {
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${P[name] || P.info}</svg>`;
}

// ---------------- glossary + tooltips
export const GLOSSARY = {
  "grounded": "Every claim in the answer can be found in the retrieved document passages or tool results.",
  "retrieval": "Finding the document passages most relevant to a question (here: embeddings + BM25 keyword search).",
  "retrieval miss": "The passage holding the answer was not among the passages retrieved, so the agent never saw it.",
  "prompt defect": "The right passage was retrieved, but the answer still missed or mangled the expected facts.",
  "hallucination": "The answer states something the documents don't support, or answers a question it should refuse.",
  "wrong refusal": "The agent declined to answer although its documents contained the answer.",
  "groundability": "Whether your documents actually contain enough to answer a topic you asked for.",
  "held-out set": "About 30% of the test questions that the optimizer and tournament never see. The score you should quote.",
  "dev set": "The 70% of test questions used to choose prompts and fixes. Scores here are optimistic.",
  "refusal gate": "A hard rule: if retrieval confidence is below a calibrated threshold, the agent refuses without guessing.",
  "judge self-test": "Before grading the agent, the judge must correctly grade planted good and bad answers.",
  "position bias": "LLM judges favour whatever they read first. ForgeAI judges twice with the order swapped and needs agreement.",
  "prompt tournament": "Three system-prompt strategies compete on the dev set; a fixed rule (not an LLM) picks the winner.",
  "eval set": "The test questions ForgeAI writes from your documents, with expected facts verified word-for-word.",
};

export function term(word, label) {
  const tip = GLOSSARY[word.toLowerCase()];
  if (!tip) return esc(label || word);
  return `<dfn class="term" tabindex="0" data-tip="${esc(tip)}" aria-label="${esc((label || word) + ": " + tip)}">${esc(label || word)}</dfn>`;
}

// ---------------- toasts
export function toast(message, kind = "info", timeout = 4500) {
  const root = document.getElementById("toasts");
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.setAttribute("role", kind === "bad" ? "alert" : "status");
  const ic = { ok: "check", bad: "warn", warn: "warn", info: "info" }[kind] || "info";
  t.innerHTML = `${icon(ic)}<div>${esc(message)}</div>`;
  root.appendChild(t);
  setTimeout(() => t.remove(), timeout);
}

// ---------------- modal (ESC closes, focus returns to the opener)
export function openModal(html, { label = "Dialog" } = {}) {
  const root = document.getElementById("modal-root");
  const opener = document.activeElement;
  root.innerHTML = `<div class="modal-backdrop" data-close><div class="modal" role="dialog" aria-modal="true" aria-label="${esc(label)}" tabindex="-1">
    <button class="icon-btn close" type="button" aria-label="Close dialog" data-close>${icon("x")}</button>${html}</div></div>`;
  const modal = root.querySelector(".modal");
  const close = () => {
    root.innerHTML = "";
    document.removeEventListener("keydown", onKey);
    if (opener && opener.focus) opener.focus();
  };
  const onKey = (e) => {
    if (e.key === "Escape") close();
    if (e.key === "Tab") { // keep focus inside the dialog
      const f = [...modal.querySelectorAll("button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])")];
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  };
  root.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", (e) => { if (e.target === el || el.matches("button")) close(); }));
  document.addEventListener("keydown", onKey);
  modal.focus();
  return { close, el: modal };
}

// ---------------- formatters
export const pct = (v) => (v === null || v === undefined || Number.isNaN(v) ? "–" : `${Math.round(v * 10) / 10}%`);
export const num = (v) => (v === null || v === undefined ? "–" : Number(v).toLocaleString());
export function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
export function ring(value, size = 160, stroke = 12, color = "var(--primary)") {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value || 0));
  return `<svg viewBox="0 0 ${size} ${size}" aria-hidden="true"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--border-soft)" stroke-width="${stroke}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - v / 100)}"/></svg>`;
}
export const scoreColor = (score, target) => (score === null || score === undefined ? "var(--muted)" : score >= target ? "var(--success)" : "var(--warning)");
export const CATEGORY = {
  retrieval_miss: { label: "Retrieval miss", color: "var(--c-retrieval)" },
  prompt_defect: { label: "Prompt defect", color: "var(--c-prompt)" },
  hallucination: { label: "Hallucination", color: "var(--c-halluc)" },
  wrong_refusal: { label: "Wrong refusal", color: "var(--c-refusal)" },
};
export const skeleton = (lines = 3) => `<div class="stack" aria-hidden="true">${Array.from({ length: lines }, (_, i) => `<div class="skel" style="height:${i ? 18 : 120}px"></div>`).join("")}</div><span class="sr-only">Loading…</span>`;
export const emptyState = (ic, title, text, action = "") => `<div class="empty">${icon(ic)}<h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;
