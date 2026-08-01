(() => {
  const filesInput = document.getElementById("pressureFiles");
  const btnStart = document.getElementById("pressureStart");
  const btnClear = document.getElementById("pressureClear");
  const concurrencyEl = document.getElementById("pressureConcurrency");
  const statusEl = document.getElementById("pressureStatus");
  const bodyEl = document.getElementById("pressureBody");
  const summaryEl = document.getElementById("pressureSummary");
  const sumDone = document.getElementById("sumDone");
  const sumCost = document.getElementById("sumCost");
  const sumAvgSec = document.getElementById("sumAvgSec");
  const sumTotalSec = document.getElementById("sumTotalSec");

  let rows = [];
  let running = false;
  let abort = false;

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function formatTokens(usage) {
    if (!usage) return "—";
    const p = usage.prompt_tokens;
    const c = usage.completion_tokens;
    const t = usage.total_tokens;
    if (p == null && c == null && t == null) return "—";
    return `${p ?? "—"} / ${c ?? "—"} / ${t ?? "—"}`;
  }

  function formatCost(usage) {
    if (!usage || usage.cost_usd == null || !(Number(usage.cost_usd) > 0)) {
      return { text: "—", usd: 0 };
    }
    const usd = Number(usage.cost_usd);
    const ntd = usd * 32;
    return {
      text: `US$${usd.toFixed(6)}\n≈ NT$${ntd.toFixed(4)}`,
      usd,
    };
  }

  function formatModel(row) {
    const model = row.model || row.usage?.model;
    if (!model) return "—";
    const short = String(model).replace(/^google\//, "");
    if (row.fallback || row.usage?.fallback) {
      return `${short}\n(fallback)`;
    }
    return short;
  }

  function revokePreviews() {
    rows.forEach((row) => {
      if (row.previewUrl) URL.revokeObjectURL(row.previewUrl);
    });
  }

  function updateSummary() {
    const done = rows.filter((r) => r.state === "done" || r.state === "error");
    const okTimed = done.filter((r) => typeof r.elapsedSec === "number");
    const totalUsd = done.reduce((acc, r) => acc + (r.costUsd || 0), 0);
    const totalSec = okTimed.reduce((acc, r) => acc + r.elapsedSec, 0);
    const avgSec = okTimed.length ? totalSec / okTimed.length : null;

    if (summaryEl) summaryEl.hidden = rows.length === 0;
    if (sumDone) sumDone.textContent = `${done.length} / ${rows.length}`;
    if (sumCost) {
      sumCost.textContent =
        totalUsd > 0
          ? `US$${totalUsd.toFixed(6)}（≈ NT$${(totalUsd * 32).toFixed(4)}）`
          : "—";
    }
    if (sumAvgSec) {
      sumAvgSec.textContent = avgSec == null ? "—" : `${avgSec.toFixed(2)} s`;
    }
    if (sumTotalSec) {
      sumTotalSec.textContent = okTimed.length ? `${totalSec.toFixed(2)} s` : "—";
    }
  }

  function renderTable() {
    if (!bodyEl) return;
    if (!rows.length) {
      bodyEl.innerHTML =
        '<tr class="pressure-empty"><td colspan="9">尚未選擇圖片</td></tr>';
      updateSummary();
      return;
    }

    bodyEl.innerHTML = rows
      .map((row, idx) => {
        const plate =
          row.state === "pending" || row.state === "running"
            ? "…"
            : row.plate || "—";
        const model =
          row.state === "pending" || row.state === "running"
            ? "…"
            : formatModel(row).replace("\n", "<br>");
        const tokens =
          row.state === "done" || row.state === "error" ? formatTokens(row.usage) : "…";
        const cost =
          row.state === "done" || row.state === "error"
            ? formatCost(row.usage).text.replace("\n", "<br>")
            : "…";
        const sec =
          typeof row.elapsedSec === "number" ? row.elapsedSec.toFixed(2) : "…";
        let stateLabel = "等待";
        if (row.state === "running") stateLabel = "辨識中";
        else if (row.state === "done") stateLabel = row.ok ? "成功" : "失敗";
        else if (row.state === "error") stateLabel = "錯誤";
        const stateClass =
          row.state === "done" && row.ok
            ? "is-ok"
            : row.state === "error" || (row.state === "done" && !row.ok)
              ? "is-bad"
              : row.state === "running"
                ? "is-run"
                : "";
        const err =
          row.error && (row.state === "error" || (row.state === "done" && !row.ok))
            ? `<div class="pressure-err">${escapeHtml(row.error)}</div>`
            : "";
        return `<tr data-idx="${idx}">
          <td>${idx + 1}</td>
          <td class="pressure-thumb-cell"><img class="pressure-thumb" src="${row.previewUrl}" alt="" /></td>
          <td class="pressure-name">${escapeHtml(row.name)}</td>
          <td class="pressure-plate">${escapeHtml(plate)}${err}</td>
          <td class="pressure-mono pressure-model">${model}</td>
          <td class="pressure-mono">${tokens}</td>
          <td class="pressure-mono pressure-cost">${cost}</td>
          <td class="pressure-mono">${sec}</td>
          <td class="pressure-state ${stateClass}">${stateLabel}</td>
        </tr>`;
      })
      .join("");
    updateSummary();
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setRunningUi(isRunning) {
    running = isRunning;
    if (btnStart) btnStart.disabled = isRunning || !rows.length;
    if (btnClear) btnClear.disabled = isRunning || !rows.length;
    if (filesInput) filesInput.disabled = isRunning;
    if (concurrencyEl) concurrencyEl.disabled = isRunning;
  }

  async function recognizeOne(row) {
    row.state = "running";
    row.error = null;
    row.model = null;
    row.fallback = false;
    renderTable();
    const form = new FormData();
    form.append("image", row.file, row.name);
    const t0 = performance.now();
    try {
      const res = await fetch("/api/recognize", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      const clientSec = (performance.now() - t0) / 1000;
      if (!res.ok) {
        row.state = "error";
        row.ok = false;
        row.error = data.detail || `HTTP ${res.status}`;
        row.elapsedSec = clientSec;
        return;
      }
      row.state = "done";
      row.ok = Boolean(data.ok);
      row.plate = data.plate_number || "";
      row.usage = data.usage || null;
      row.model = data.model || data.usage?.model || null;
      row.fallback = Boolean(data.usage?.fallback);
      row.costUsd = formatCost(row.usage).usd;
      row.elapsedSec =
        typeof data.elapsed_sec === "number" ? data.elapsed_sec : clientSec;
      row.error = data.error || (!data.ok ? "辨識失敗" : null);
    } catch (err) {
      row.state = "error";
      row.ok = false;
      row.error = err.message || String(err);
      row.elapsedSec = (performance.now() - t0) / 1000;
    } finally {
      renderTable();
    }
  }

  async function runQueue() {
    abort = false;
    setRunningUi(true);
    const concurrency = Math.max(
      1,
      Math.min(3, Number(concurrencyEl?.value || 1) || 1)
    );
    setStatus(`測試中（並行 ${concurrency}）…`);

    let next = 0;
    async function worker() {
      while (!abort) {
        const idx = next++;
        if (idx >= rows.length) return;
        await recognizeOne(rows[idx]);
      }
    }

    await Promise.all(Array.from({ length: concurrency }, () => worker()));

    setRunningUi(false);
    const done = rows.filter((r) => r.state === "done" || r.state === "error");
    const ok = rows.filter((r) => r.state === "done" && r.ok).length;
    const fb = rows.filter((r) => r.fallback).length;
    setStatus(`完成：成功 ${ok} / ${done.length}${fb ? `（fallback ${fb}）` : ""}`);
    updateSummary();
  }

  function loadFiles(fileList) {
    revokePreviews();
    const files = Array.from(fileList || []).filter((f) =>
      (f.type || "").startsWith("image/")
    );
    rows = files.map((file) => ({
      file,
      name: file.name,
      previewUrl: URL.createObjectURL(file),
      state: "pending",
      ok: false,
      plate: "",
      model: null,
      fallback: false,
      usage: null,
      costUsd: 0,
      elapsedSec: null,
      error: null,
    }));
    if (btnStart) btnStart.disabled = !rows.length;
    if (btnClear) btnClear.disabled = !rows.length;
    setStatus(rows.length ? `已選 ${rows.length} 張，可開始測試` : "選擇多張圖片後開始");
    renderTable();
  }

  filesInput?.addEventListener("change", () => {
    loadFiles(filesInput.files);
  });

  btnStart?.addEventListener("click", () => {
    if (running || !rows.length) return;
    rows.forEach((r) => {
      r.state = "pending";
      r.ok = false;
      r.plate = "";
      r.model = null;
      r.fallback = false;
      r.usage = null;
      r.costUsd = 0;
      r.elapsedSec = null;
      r.error = null;
    });
    renderTable();
    runQueue();
  });

  btnClear?.addEventListener("click", () => {
    if (running) return;
    revokePreviews();
    rows = [];
    if (filesInput) filesInput.value = "";
    if (btnStart) btnStart.disabled = true;
    if (btnClear) btnClear.disabled = true;
    setStatus("選擇多張圖片後開始");
    renderTable();
  });

  window.__pageCleanup = () => {
    abort = true;
    revokePreviews();
    rows = [];
  };
})();
