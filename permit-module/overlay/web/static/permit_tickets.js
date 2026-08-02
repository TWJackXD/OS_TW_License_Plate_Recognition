(() => {
  const listEl = document.getElementById("ticketList");
  const emptyEl = document.getElementById("ticketEmpty");
  const msg = document.getElementById("ticketMsg");
  const printRoot = document.getElementById("printRoot");
  const reloadBtn = document.getElementById("reloadBtn");
  const selectAllBtn = document.getElementById("selectAllBtn");
  const clearSelBtn = document.getElementById("clearSelBtn");
  const deleteSelBtn = document.getElementById("deleteSelBtn");
  const pdfBtn = document.getElementById("pdfBtn");
  const printB1Btn = document.getElementById("printB1Btn");
  const btnConnectPrinter = document.getElementById("btnConnectPrinter");
  const printerPill = document.getElementById("printerPill");
  const printerPillText = document.getElementById("printerPillText");
  const { showMsg, escapeHtml } = window.PermitUI;

  const PAPER_W_MM = 58;
  const PAPER_H_MM = 80;

  /** @type {{key:string, selected:boolean, violation:any, permit:any|null}[]} */
  let rows = [];
  let loading = false;
  let busy = false;

  function selectedRows() {
    return rows.filter((r) => r.selected);
  }

  function setPrinterPill(text, ready) {
    if (!printerPillText) return;
    printerPillText.textContent = text;
    if (printerPill) printerPill.classList.toggle("is-ready", !!ready);
  }

  function syncButtons() {
    const n = selectedRows().length;
    deleteSelBtn.disabled = busy || !n;
    pdfBtn.disabled = busy || !n;
    deleteSelBtn.textContent = n ? `刪除選取（${n}）` : "刪除選取";
    pdfBtn.textContent = n ? `下載合併 PDF（${n}）` : "下載合併 PDF";
    if (printB1Btn) {
      printB1Btn.disabled = busy || !n;
      printB1Btn.textContent = n ? `B1 列印選取（${n}）` : "B1 列印選取";
    }
  }

  function formatTime(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString("zh-TW", { hour12: false });
    } catch {
      return String(value);
    }
  }

  function formatLocation(v) {
    if (v && v.location_name) {
      return String(v.location_name).replaceAll("財經學院", "財金學院");
    }
    if (v && v.latitude != null && v.longitude != null) {
      return `校區範圍（${Number(v.latitude).toFixed(5)}, ${Number(v.longitude).toFixed(5)}）`;
    }
    return "本校校區範圍內";
  }

  function docNo(v) {
    if (v && v.id != null && v.id !== "") {
      return `NKUST-${String(v.id).padStart(6, "0")}`;
    }
    const plate = String((v && v.plate_number) || "XXXX")
      .replace(/[^A-Z0-9]/gi, "")
      .slice(0, 8);
    return `NKUST-${plate || "000000"}`;
  }

  function ticketHtml(violation, permit) {
    const printedAt = new Date().toLocaleString("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    return `
<article class="ticket">
  <header class="ticket__head">
    <p class="ticket__org">國立高雄科技大學</p>
    <h1 class="ticket__title">校園車輛違規罰單</h1>
    <p class="ticket__docno">單號：${escapeHtml(docNo(violation))}</p>
  </header>
  <table class="ticket__table">
    <tbody>
      <tr><th>車牌號碼</th><td class="ticket__plate" colspan="3">${escapeHtml(violation.plate_number)}</td></tr>
      <tr><th>違規時間</th><td colspan="3">${escapeHtml(formatTime(violation.created_at))}</td></tr>
      <tr><th>違規地點</th><td colspan="3">${escapeHtml(formatLocation(violation))}</td></tr>
      <tr><th>違規事實</th><td colspan="3">${escapeHtml(violation.reason || "—")}</td></tr>
      <tr>
        <th>車主姓名</th><td class="ticket__name">${escapeHtml((permit && permit.name) || "（未登記車證）")}</td>
        <th class="ticket__sid-label">學號</th><td class="ticket__sid">${escapeHtml((permit && permit.student_id) || "—")}</td>
      </tr>
      <tr>
        <th>所屬校區</th><td class="ticket__name">${escapeHtml((permit && permit.campus) || "—")}</td>
        <th class="ticket__sid-label">系級</th><td class="ticket__sid">${escapeHtml((permit && permit.department) || "—")}</td>
      </tr>
    </tbody>
  </table>
  <section class="ticket__block">
    <p class="ticket__label">裁處依據</p>
    <p>依本校校園車輛管理相關規定，上開車輛有違規情事，特此舉發。</p>
  </section>
  <section class="ticket__block">
    <p class="ticket__label">應辦事項</p>
    <ol class="ticket__list">
      <li>請於七日內向本校相關單位辦理。</li>
      <li>如有異議，請檢具證明文件提出申訴。</li>
      <li>逾期未辦，得依規定加重處理。</li>
    </ol>
  </section>
  <table class="ticket__table ticket__table--sign">
    <tbody>
      <tr><th>舉發單位</th><td>校園安全管理／停車管理</td></tr>
      <tr><th>列印時間</th><td>${escapeHtml(printedAt)}</td></tr>
    </tbody>
  </table>
  <p class="ticket__footer-note">本單由系統自動產製，請妥為保存。</p>
</article>`;
  }

  function renderList() {
    if (!rows.length) {
      listEl.innerHTML = "";
      emptyEl.hidden = false;
      printRoot.innerHTML = "";
      syncButtons();
      return;
    }
    emptyEl.hidden = true;
    listEl.innerHTML = rows
      .map(
        (row, idx) => `
      <div class="ticket-item" data-idx="${idx}">
        <label class="ticket-item__check">
          <input type="checkbox" ${row.selected ? "checked" : ""} data-role="sel" />
        </label>
        <div class="ticket-item__body">
          <strong>${escapeHtml(row.violation.plate_number)}</strong>
          <div class="ticket-item__meta">
            ${escapeHtml(row.violation.created_at || "")} · ${escapeHtml(row.violation.reason || "")}
            ${row.violation.location_name ? ` · ${escapeHtml(row.violation.location_name)}` : ""}
          </div>
        </div>
        <span class="permit-badge ${row.permit ? "permit-badge--ok" : "permit-badge--none"}">
          ${escapeHtml(row.permit ? row.permit.name : "無車證")}
        </span>
        <button type="button" class="md-btn md-btn--danger" data-role="del">刪除</button>
      </div>`
      )
      .join("");

    listEl.querySelectorAll(".ticket-item").forEach((el) => {
      const idx = Number(el.getAttribute("data-idx"));
      el.querySelector('[data-role="sel"]').addEventListener("change", (ev) => {
        rows[idx].selected = ev.target.checked;
        syncButtons();
        renderPrint();
      });
      el.querySelector('[data-role="del"]').addEventListener("click", () => deleteOne(rows[idx]));
    });
    renderPrint();
    syncButtons();
  }

  function renderPrint() {
    printRoot.innerHTML = selectedRows()
      .map((r) => ticketHtml(r.violation, r.permit))
      .join("");
  }

  async function enrich(items) {
    const next = [];
    for (const item of items) {
      const plate = String(item.plate_number || "").trim();
      if (!plate) continue;
      let permit = null;
      try {
        const res = await window.PermitAPI.lookup(plate);
        permit = res.found ? res.permit : null;
      } catch {
        permit = null;
      }
      next.push({
        key: `${item.id ?? plate}-${item.created_at ?? next.length}`,
        selected: true,
        violation: item,
        permit,
      });
    }
    return next;
  }

  async function load() {
    loading = true;
    reloadBtn.disabled = true;
    showMsg(msg, "");
    try {
      const data = await window.PermitAPI.listViolations(500);
      const items = data.items || [];
      rows = await enrich(items);
      renderList();
      showMsg(
        msg,
        items.length ? `已載入 ${rows.length} 筆違規` : "尚無違規資料",
        items.length ? "ok" : "warn"
      );
    } catch (err) {
      rows = [];
      renderList();
      showMsg(msg, err.message || String(err), "error");
    } finally {
      loading = false;
      reloadBtn.disabled = false;
    }
  }

  async function deleteOne(row) {
    const id = row && row.violation && row.violation.id;
    if (id == null) {
      showMsg(msg, "此筆沒有可刪除的 id", "error");
      return;
    }
    if (!confirm(`確定刪除車牌 ${row.violation.plate_number} 的違規紀錄？`)) return;
    busy = true;
    syncButtons();
    try {
      await window.PermitAPI.deleteViolation(id);
      rows = rows.filter((r) => r.key !== row.key);
      renderList();
      showMsg(msg, `已刪除 ${row.violation.plate_number}`, "ok");
    } catch (err) {
      showMsg(msg, err.message || String(err), "error");
    } finally {
      busy = false;
      syncButtons();
    }
  }

  async function deleteSelected() {
    const targets = selectedRows().filter((r) => r.violation && r.violation.id != null);
    if (!targets.length) return;
    if (!confirm(`確定刪除選取的 ${targets.length} 筆違規紀錄？`)) return;
    busy = true;
    syncButtons();
    try {
      for (const row of targets) {
        await window.PermitAPI.deleteViolation(row.violation.id);
      }
      const removed = new Set(targets.map((r) => r.key));
      rows = rows.filter((r) => !removed.has(r.key));
      renderList();
      showMsg(msg, `已刪除 ${targets.length} 筆`, "ok");
    } catch (err) {
      showMsg(msg, err.message || String(err), "error");
      await load();
    } finally {
      busy = false;
      syncButtons();
    }
  }

  function waitFrames(n = 2) {
    return new Promise((resolve) => {
      const step = () => {
        if (n <= 0) resolve();
        else {
          n -= 1;
          requestAnimationFrame(step);
        }
      };
      requestAnimationFrame(step);
    });
  }

  async function printPdf() {
    const targets = selectedRows();
    if (!targets.length) return;
    if (!window.jspdf) {
      showMsg(msg, "PDF 函式庫尚未載入，請稍後再試", "error");
      return;
    }
    busy = true;
    syncButtons();
    showMsg(msg, "");
    try {
      const { jsPDF } = window.jspdf;
      const pdf = new jsPDF({
        unit: "mm",
        format: [PAPER_W_MM, PAPER_H_MM],
        orientation: "portrait",
      });

      // Prefer B1 canvas (384×640) when Niimbot helper is loaded — same layout as thermal print.
      if (window.NiimbotPrint && typeof window.NiimbotPrint.renderTicketCanvas === "function") {
        if (typeof window.NiimbotPrint.ensureFonts === "function") {
          await window.NiimbotPrint.ensureFonts();
        }
        for (let i = 0; i < targets.length; i += 1) {
          if (i > 0) pdf.addPage([PAPER_W_MM, PAPER_H_MM], "portrait");
          const canvas = window.NiimbotPrint.renderTicketCanvas(
            targets[i].violation,
            targets[i].permit
          );
          const img = canvas.toDataURL("image/jpeg", 0.95);
          pdf.addImage(img, "JPEG", 0, 0, PAPER_W_MM, PAPER_H_MM);
        }
      } else {
        if (!window.html2canvas) {
          throw new Error("PDF 函式庫尚未載入，請稍後再試");
        }
        renderPrint();
        printRoot.classList.add("print-area--capturing");
        await waitFrames(2);
        const tickets = [...printRoot.querySelectorAll(".ticket")];
        if (!tickets.length) throw new Error("沒有可列印的罰單內容");
        for (let i = 0; i < tickets.length; i += 1) {
          if (i > 0) pdf.addPage([PAPER_W_MM, PAPER_H_MM], "portrait");
          const canvas = await window.html2canvas(tickets[i], {
            scale: 3,
            useCORS: true,
            logging: false,
            backgroundColor: "#ffffff",
            scrollX: 0,
            scrollY: -window.scrollY,
            width: 219,
            height: 302,
          });
          const img = canvas.toDataURL("image/jpeg", 0.98);
          pdf.addImage(img, "JPEG", 0, 0, PAPER_W_MM, PAPER_H_MM);
        }
      }

      const stamp = new Date().toISOString().slice(0, 10);
      pdf.save(`tickets-58x80-${stamp}.pdf`);
      showMsg(msg, `已下載 ${targets.length} 張 58×80mm 罰單 PDF`, "ok");
    } catch (err) {
      showMsg(msg, err.message || String(err), "error");
    } finally {
      printRoot.classList.remove("print-area--capturing");
      busy = false;
      syncButtons();
    }
  }

  async function printB1Selected() {
    const targets = selectedRows();
    if (!targets.length) return;
    if (!window.NiimbotPrint) {
      showMsg(msg, "Niimbot 列印模組未載入", "error");
      return;
    }
    busy = true;
    syncButtons();
    setPrinterPill("列印中…", false);
    showMsg(msg, "");
    let ok = 0;
    try {
      for (const row of targets) {
        await window.NiimbotPrint.printTicket({
          violation: row.violation,
          permit: row.permit,
        });
        ok += 1;
        showMsg(msg, `已列印 ${ok}／${targets.length}…`, "ok");
      }
      setPrinterPill(`已連線 · 列印完成（${ok}）`, true);
      showMsg(msg, `已送出 ${ok} 張 B1 罰單列印`, "ok");
    } catch (err) {
      setPrinterPill("列印失敗", false);
      showMsg(
        msg,
        ok ? `已列印 ${ok} 張後失敗：${err.message || err}` : err.message || String(err),
        "error"
      );
    } finally {
      busy = false;
      syncButtons();
    }
  }

  reloadBtn.addEventListener("click", () => {
    if (!loading) load();
  });
  selectAllBtn.addEventListener("click", () => {
    rows.forEach((r) => {
      r.selected = true;
    });
    renderList();
  });
  clearSelBtn.addEventListener("click", () => {
    rows.forEach((r) => {
      r.selected = false;
    });
    renderList();
  });
  deleteSelBtn.addEventListener("click", deleteSelected);
  pdfBtn.addEventListener("click", printPdf);
  if (printB1Btn) printB1Btn.addEventListener("click", printB1Selected);

  if (btnConnectPrinter) {
    btnConnectPrinter.addEventListener("click", async () => {
      if (!window.NiimbotPrint) {
        setPrinterPill("列印模組未載入", false);
        return;
      }
      btnConnectPrinter.disabled = true;
      setPrinterPill("配對中…", false);
      try {
        const info = await window.NiimbotPrint.connect();
        const label = (info && (info.label || info.modelId)) || "B1";
        setPrinterPill(`已連線 ${label}`, true);
      } catch (err) {
        setPrinterPill("連接失敗", false);
        showMsg(msg, err.message || String(err), "error");
      } finally {
        btnConnectPrinter.disabled = false;
      }
    });
    if (window.NiimbotPrint && !window.NiimbotPrint.isSupported()) {
      setPrinterPill("瀏覽器不支援 Bluetooth", false);
      btnConnectPrinter.disabled = true;
    }
  }

  load();
})();
