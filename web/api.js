// Thin client for the ForgeAI REST + SSE API. Errors become friendly messages with a next step.

const FRIENDLY = {
  0: "Can't reach the ForgeAI server. Is `python run.py` still running?",
  404: "That item doesn't exist any more. Refresh the page and try again.",
  409: "That action isn't possible right now (the run has moved on).",
  500: "The server hit an unexpected error. Check the terminal running ForgeAI for details.",
};

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function request(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, opts);
  } catch {
    throw new ApiError(FRIENDLY[0], 0);
  }
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json().catch(() => ({})) : await r.text();
  if (!r.ok) {
    const detail = (body && body.error) || (typeof body === "string" ? body : "");
    throw new ApiError(detail || FRIENDLY[r.status] || `Request failed (${r.status})`, r.status);
  }
  return body;
}

const json = (method, body) => ({ method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  stats: () => request("/api/stats"),
  demos: () => request("/api/demos"),
  loadDemo: (id) => request(`/api/demos/${encodeURIComponent(id)}/load`, { method: "POST" }),
  runs: () => request("/api/runs"),
  run: (id) => request(`/api/runs/${encodeURIComponent(id)}`),
  bundle: (id) => request(`/api/runs/${encodeURIComponent(id)}/bundle`),
  startRun: (formData) => request("/api/runs", { method: "POST", body: formData }),
  answers: (id, answers, auto = false) => request(`/api/runs/${encodeURIComponent(id)}/answers`, json("POST", { answers, auto })),
  approval: (id, action, requirements = null) => request(`/api/runs/${encodeURIComponent(id)}/approval`, json("POST", { action, requirements })),
  chat: (runId, message) => request("/api/chat", json("POST", { run_id: runId, message })),
  regress: (id, formData) => request(`/api/runs/${encodeURIComponent(id)}/regress`, { method: "POST", body: formData }),
  requirementsStatus: (runId) => request(`/api/requirements-status${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`),
  artifactUrl: (id, name) => `/api/runs/${encodeURIComponent(id)}/artifacts/${name}`,
  zipUrl: (id) => `/api/runs/${encodeURIComponent(id)}/zip`,
};

const EVENT_TYPES = ["stage_started", "stage_done", "questions_asked", "flags", "approval_requested", "iteration_result", "error", "log", "finished"];

/** Subscribe to a run's event stream. Returns a close() function. */
export function streamEvents(runId, onEvent, onEnd) {
  const src = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);
  let ended = false;
  EVENT_TYPES.forEach((t) => src.addEventListener(t, (m) => {
    let ev;
    try { ev = JSON.parse(m.data); } catch { return; }
    onEvent(ev);
    if (t === "finished") { ended = true; src.close(); onEnd && onEnd(ev); }
  }));
  src.onerror = () => { if (!ended) { src.close(); onEnd && onEnd(null); } };
  return () => src.close();
}
