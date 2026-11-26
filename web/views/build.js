// Build form: brief, documents (or a demo), options. Starting a build navigates to the live run view.
import { api } from "../api.js";
import { esc, icon, term, toast } from "../ui.js";

const ACCEPT = [".txt", ".md", ".pdf", ".docx", ".csv"];
const kb = (b) => (b < 1024 ? `${b} B` : `${Math.round(b / 1024)} KB`);

export async function mount(root, { query }) {
  let demo = null;
  let files = [];
  root.innerHTML = `
  <div class="wrap">
    <div class="page-head">
      <span class="eyebrow">Build</span>
      <h1>Build an agent</h1>
      <p>Describe the assistant in one paragraph and add the documents it should know. ForgeAI interviews you, builds the agent, tests it and improves it.</p>
    </div>
    <form id="build-form" class="grid grid-2" novalidate>
      <div class="card stack">
        <div>
          <label class="field" for="brief">1. Describe the assistant you need</label>
          <textarea class="input" id="brief" name="brief" rows="6" maxlength="3000" aria-describedby="brief-help brief-err"
            placeholder="I need an assistant that answers HR policy questions for shore staff: leave, conduct, travel and expenses."></textarea>
          <span class="helper" id="brief-help">Who is it for, and which topics must it cover? One paragraph is enough. <span id="brief-count">0</span>/3000</span>
          <span class="helper" id="brief-err" role="alert" style="color:var(--danger)"></span>
        </div>
        <div>
          <span class="field" id="docs-label" style="display:block;font-weight:700;color:var(--heading);margin-bottom:6px">2. Add its documents</span>
          <div id="demo-chip"></div>
          <label class="dropzone" id="dropzone" for="files" aria-describedby="docs-help">
            ${icon("upload")}
            <div><strong>Drop files here</strong> or <u>browse</u></div>
            <span class="helper" id="docs-help">PDF, Word (.docx), Markdown, text or CSV. Scanned PDFs without text are skipped with a warning.</span>
          </label>
          <input class="sr-only" type="file" id="files" multiple accept="${ACCEPT.join(",")}" aria-labelledby="docs-label">
          <ul class="file-list" id="file-list" aria-label="Selected documents"></ul>
          <span class="helper" id="docs-err" role="alert" style="color:var(--danger)"></span>
        </div>
      </div>
      <div class="card stack">
        <span class="field" style="font-weight:700;color:var(--heading)">3. Choose how ForgeAI works with you</span>
        <label class="toggle-card"><input type="checkbox" id="opt-ask" checked>
          <div><strong>Ask me clarifying questions</strong><span>Up to 5 short questions. Untick for a fully unattended build (ForgeAI answers them itself).</span></div></label>
        <label class="toggle-card"><input type="checkbox" id="opt-approve">
          <div><strong>Let me review the requirements first</strong><span>Pauses before anything is generated so you can approve, edit or reject the plan.</span></div></label>
        <label class="toggle-card"><input type="checkbox" id="opt-tournament" checked>
          <div><strong>Run a ${term("prompt tournament")}</strong><span>Three prompt strategies compete on the test set; a fixed rule picks the winner. Uses more tokens.</span></div></label>
        <details>
          <summary class="small" style="cursor:pointer;font-weight:600">Advanced</summary>
          <div style="margin-top:10px">
            <label class="field" for="opt-seed">Random seed</label>
            <input class="input" id="opt-seed" type="number" min="0" value="42" style="max-width:160px" aria-describedby="seed-help">
            <span class="helper" id="seed-help">Same seed + same inputs = same test split and sampling. Stored in the run's metadata.</span>
          </div>
        </details>
        <div>
          <button class="btn btn-primary" type="submit" id="build-btn">${icon("play")}Build agent</button>
          <span class="helper">Takes seconds with the mock model and a few minutes with a real one. You can watch every step live.</span>
        </div>
      </div>
    </form>
  </div>`;

  const $ = (s) => root.querySelector(s);
  const brief = $("#brief");
  brief.addEventListener("input", () => { $("#brief-count").textContent = brief.value.length; $("#brief-err").textContent = ""; });

  function paintFiles() {
    $("#file-list").innerHTML = files.map((f, i) => `<li>${icon("doc")}<span class="name">${esc(f.name)}</span><span class="muted small">${kb(f.size)}</span>
      <button class="btn btn-ghost btn-sm" type="button" data-rm="${i}" aria-label="Remove ${esc(f.name)}">${icon("x")}</button></li>`).join("");
    root.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { files.splice(+b.dataset.rm, 1); paintFiles(); }));
  }
  function addFiles(list) {
    for (const f of list) {
      const ok = ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext));
      if (!ok) { toast(`${f.name}: unsupported type. Use ${ACCEPT.join(", ")}.`, "warn"); continue; }
      if (!files.some((x) => x.name === f.name)) files.push(f);
    }
    $("#docs-err").textContent = "";
    paintFiles();
  }
  $("#files").addEventListener("change", (e) => addFiles(e.target.files));
  const dz = $("#dropzone");
  ["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

  function paintDemo() {
    $("#demo-chip").innerHTML = demo ? `<div class="callout" style="margin-bottom:10px">${icon("doc")}<div><p><strong>${esc(demo.title)} demo documents attached</strong></p>
      <ul class="file-list">${demo.files.map((f) => `<li>${icon("doc")}<span class="name">${esc(f.name)}</span><span class="muted small">${kb(f.bytes)}</span></li>`).join("")}</ul>
      <button class="btn btn-ghost btn-sm" type="button" id="demo-clear" style="margin-top:8px">Remove demo documents</button></div></div>` : "";
    if (demo) $("#demo-clear").addEventListener("click", () => { demo = null; paintDemo(); });
  }

  const demoId = query.get("demo");
  if (demoId) {
    try {
      demo = await api.loadDemo(demoId);
      brief.value = demo.brief;
      brief.dispatchEvent(new Event("input"));
      paintDemo();
      toast(`Loaded the ${demo.title} demo. Review the brief, then press Build agent.`, "ok");
    } catch (e) { toast(e.message, "bad"); }
  }

  $("#build-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    let bad = false;
    if (!brief.value.trim()) { $("#brief-err").textContent = "Write a short brief first: who the assistant is for and what it should answer."; bad = true; }
    if (!files.length && !demo) { $("#docs-err").textContent = "Add at least one document, or pick a demo on the home page."; bad = true; }
    if (bad) { (brief.value.trim() ? dz : brief).focus(); return; }
    const fd = new FormData();
    fd.append("brief", brief.value.trim());
    files.forEach((f) => fd.append("files", f));
    if (demo) fd.append("demo", demo.id);
    fd.append("non_interactive", String(!$("#opt-ask").checked));
    fd.append("approve", String($("#opt-approve").checked));
    fd.append("tournament", String($("#opt-tournament").checked));
    fd.append("seed", $("#opt-seed").value || "42");
    const btn = $("#build-btn");
    btn.disabled = true;
    btn.innerHTML = `<span class="typing"><i></i><i></i><i></i></span> Starting…`;
    try {
      const { run_id, warnings } = await api.startRun(fd);
      (warnings || []).forEach((w) => toast(w, "warn"));
      location.hash = `#/run/${run_id}`;
    } catch (err) {
      toast(`Couldn't start the build: ${err.message}`, "bad", 7000);
      btn.disabled = false;
      btn.innerHTML = `${icon("play")}Build agent`;
    }
  });
}
