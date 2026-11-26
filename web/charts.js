// Dependency-free inline SVG charts with keyboard-reachable tooltips.
import { esc, CATEGORY } from "./ui.js";

/** points: [{label, value, kind: "baseline"|"kept"|"reverted"}], target: number, heldout: number|null */
export function lineChart({ points, target, heldout }) {
  const W = 640, H = 260, L = 44, R = 96, T = 26, B = 40;
  const n = Math.max(points.length, 1);
  const x = (i) => L + (n === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (n - 1));
  const y = (v) => T + (1 - v / 100) * (H - T - B);
  const grid = [0, 25, 50, 75, 100].map((v) => `<line class="grid-line" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join("");
  const tgt = target != null ? `<line class="target" x1="${L}" x2="${W - R}" y1="${y(target)}" y2="${y(target)}"/>` : "";
  // the agent's real trajectory skips reverted attempts
  let path = "", last = null;
  const dashes = [];
  points.forEach((p, i) => {
    if (p.kind === "reverted") { if (last) dashes.push(`<line x1="${x(last.i)}" y1="${y(last.v)}" x2="${x(i)}" y2="${y(p.value)}" stroke="var(--danger)" stroke-width="2" stroke-dasharray="4 4"/>`); return; }
    path += `${path ? "L" : "M"}${x(i)},${y(p.value)} `;
    last = { i, v: p.value };
  });
  const dots = points.map((p, i) => {
    const tip = `${p.label}: ${p.value}%${p.kind === "reverted" ? " (reverted: score dropped)" : ""}`;
    return `<g><circle class="pt ${p.kind === "reverted" ? "reverted" : ""}" cx="${x(i)}" cy="${y(p.value)}" r="7" tabindex="0" role="img" aria-label="${esc(tip)}" data-tip="${esc(tip)}"><title>${esc(tip)}</title></circle>
      <text x="${x(i)}" y="${H - 14}" text-anchor="middle">${esc(p.label)}</text><text class="bar-label" x="${x(i)}" y="${y(p.value) - 12}" text-anchor="middle">${p.value}</text></g>`;
  }).join("");
  const ho = heldout != null ? `<g><rect class="pt heldout" x="${W - R + 44}" y="${y(heldout) - 7}" width="14" height="14" rx="3" tabindex="0" role="img" aria-label="Held-out score ${heldout}%" data-tip="Held-out score (never seen by the optimizer): ${heldout}%"><title>Held-out score ${heldout}%</title></rect>
    <text x="${W - R + 51}" y="${H - 14}" text-anchor="middle">held-out</text><text class="bar-label" x="${W - R + 51}" y="${y(heldout) - 12}" text-anchor="middle">${heldout}</text></g>` : "";
  const summary = `Dev-set score per iteration: ${points.map((p) => `${p.label} ${p.value}%${p.kind === "reverted" ? " reverted" : ""}`).join(", ")}${heldout != null ? `; held-out ${heldout}%` : ""}.`;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(summary)}">${grid}${tgt}${dashes.join("")}<path class="line" d="${path}"/>${dots}${ho}</svg>`;
}

/** bars: [{label, counts: {category: n}}] */
export function stackedBars(bars) {
  const W = 640, H = 240, L = 36, R = 12, T = 22, B = 38;
  const max = Math.max(1, ...bars.map((b) => Object.values(b.counts || {}).reduce((a, c) => a + c, 0)));
  const bw = Math.min(72, ((W - L - R) / Math.max(bars.length, 1)) * 0.55);
  const step = (W - L - R) / Math.max(bars.length, 1);
  const y = (v) => T + (1 - v / max) * (H - T - B);
  const ticks = [...new Set([0, Math.ceil(max / 2), max])].map((v) => `<line class="grid-line" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join("");
  const cols = bars.map((b, i) => {
    const cx = L + step * i + step / 2;
    let acc = 0, segs = "";
    for (const [cat, meta] of Object.entries(CATEGORY)) {
      const v = (b.counts || {})[cat] || 0;
      if (!v) continue;
      const tip = `${b.label}: ${v} ${meta.label.toLowerCase()}${v > 1 ? "s" : ""}`;
      segs += `<rect x="${cx - bw / 2}" y="${y(acc + v)}" width="${bw}" height="${y(acc) - y(acc + v)}" fill="${meta.color}" rx="3" tabindex="0" role="img" aria-label="${esc(tip)}" data-tip="${esc(tip)}"><title>${esc(tip)}</title></rect>`;
      acc += v;
    }
    const total = acc ? `<text class="bar-label" x="${cx}" y="${y(acc) - 6}" text-anchor="middle">${acc}</text>` : `<text x="${cx}" y="${y(0) - 6}" text-anchor="middle">0</text>`;
    return `${segs}${total}<text x="${cx}" y="${H - 14}" text-anchor="middle">${esc(b.label)}</text>`;
  }).join("");
  const summary = "Failures by category: " + bars.map((b) => `${b.label}: ${Object.entries(b.counts || {}).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(", ") || "none"}`).join("; ");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(summary)}">${ticks}${cols}</svg>`;
}

export function legend() {
  return `<div class="legend" aria-hidden="true">${Object.values(CATEGORY).map((m) => `<span><i style="background:${m.color}"></i>${m.label}</span>`).join("")}</div>`;
}

/** One floating tooltip for every [data-tip] chart element (hover and keyboard focus). */
export function enableChartTips(root) {
  let tip = document.querySelector(".chart-tip");
  if (!tip) { tip = document.createElement("div"); tip.className = "chart-tip"; tip.setAttribute("aria-hidden", "true"); document.body.appendChild(tip); }
  const show = (el, x, y) => { tip.textContent = el.dataset.tip; tip.style.left = `${Math.min(x + 12, innerWidth - 270)}px`; tip.style.top = `${y - 36}px`; tip.style.opacity = 1; };
  const hide = () => { tip.style.opacity = 0; };
  root.querySelectorAll(".chart [data-tip]").forEach((el) => {
    el.addEventListener("mousemove", (e) => show(el, e.clientX, e.clientY));
    el.addEventListener("mouseleave", hide);
    el.addEventListener("focus", () => { const r = el.getBoundingClientRect(); show(el, r.right, r.top); });
    el.addEventListener("blur", hide);
  });
}
