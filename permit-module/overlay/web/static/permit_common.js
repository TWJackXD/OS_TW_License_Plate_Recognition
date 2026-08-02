async function permitRequest(path, options = {}) {
  const res = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = data && data.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
          : `HTTP ${res.status}`;
    throw new Error(message);
  }
  return data;
}

function showMsg(el, text, kind) {
  if (!el) return;
  el.hidden = !text;
  el.textContent = text || "";
  el.classList.remove("permit-msg--ok", "permit-msg--error", "permit-msg--warn");
  if (kind) el.classList.add(`permit-msg--${kind}`);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

window.PermitAPI = {
  lookup: (plate) =>
    permitRequest(`/api/permits?plate=${encodeURIComponent(plate.trim())}`),
  list: () => permitRequest("/api/permits"),
  create: (payload) =>
    permitRequest("/api/permits", { method: "POST", body: JSON.stringify(payload) }),
  update: (id, payload) =>
    permitRequest(`/api/permits/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  remove: (id) => permitRequest(`/api/permits/${id}`, { method: "DELETE" }),
  listViolations: (limit = 500) =>
    permitRequest(`/api/violations?limit=${limit}`),
  deleteViolation: (id) =>
    permitRequest(`/api/violations/${id}`, { method: "DELETE" }),
};

window.PermitUI = { showMsg, escapeHtml };
