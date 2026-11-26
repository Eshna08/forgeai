// App shell: loader, theme, hash router.
import { icon } from "./ui.js";
import { openHow } from "./views/how.js";
import * as home from "./views/home.js";
import * as build from "./views/build.js";
import * as run from "./views/run.js";
import * as chat from "./views/chat.js";
import * as runs from "./views/runs.js";
import * as requirements from "./views/requirements.js";

const main = document.getElementById("main");
const ROUTES = { "": home, build, run, chat, runs, requirements };
let current = null;

// ---------- loader: <= 1 second, skipped on repeat visits and for reduced motion
(function loader() {
  const el = document.getElementById("loader");
  let seen = false;
  try { seen = localStorage.getItem("forge-seen") === "1"; localStorage.setItem("forge-seen", "1"); } catch {}
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (seen || reduced) { el.remove(); return; }
  const pct = document.getElementById("loader-pct"), bar = document.getElementById("loader-bar");
  const t0 = performance.now(), D = 700;
  const tick = (t) => {
    const p = Math.min(1, (t - t0) / D);
    const v = Math.round(100 * (1 - Math.pow(1 - p, 3)));
    pct.textContent = `${v}%`; bar.style.width = `${v}%`;
    if (p < 1) requestAnimationFrame(tick);
    else { el.classList.add("done"); setTimeout(() => el.remove(), 300); }
  };
  requestAnimationFrame(tick);
})();

// ---------- theme toggle (system default; manual choice persists)
const themeBtn = document.getElementById("theme-btn");
function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
function paintThemeBtn() {
  const dark = isDark();
  themeBtn.innerHTML = icon(dark ? "sun" : "moon");
  themeBtn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  themeBtn.setAttribute("aria-pressed", String(dark));
}
themeBtn.addEventListener("click", () => {
  const next = isDark() ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("forge-theme", next); } catch {}
  paintThemeBtn();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paintThemeBtn);
paintThemeBtn();
document.getElementById("how-btn").addEventListener("click", openHow);

// ---------- router: #/<view>/<param>?query
function parse() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const [view = "", ...rest] = path.split("/");
  return { view, param: decodeURIComponent(rest.join("/")), query: new URLSearchParams(query) };
}

async function route() {
  const r = parse();
  if (r.view === "how") { openHow(); history.replaceState(null, "", "#/"); r.view = ""; }
  const mod = ROUTES[r.view] || home;
  if (current && current.unmount) current.unmount();
  current = mod;
  document.querySelectorAll(".nav a").forEach((a) => {
    const active = a.dataset.route === (r.view === "run" ? "build" : r.view || "home");
    if (active) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  main.innerHTML = "";
  window.scrollTo(0, 0);
  try {
    await mod.mount(main, r);
  } catch (e) {
    main.innerHTML = `<div class="wrap section"><div class="callout bad">${icon("warn")}<p><strong>This page couldn't load.</strong> ${e.message}. Try refreshing; if it keeps happening, check the terminal running ForgeAI.</p></div></div>`;
  }
  if (r.view) main.focus({ preventScroll: true });
}
addEventListener("hashchange", route);
route();
