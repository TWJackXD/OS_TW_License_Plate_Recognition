(() => {
  const form = document.getElementById("lookupForm");
  const plateInput = document.getElementById("plate");
  const btn = document.getElementById("lookupBtn");
  const msg = document.getElementById("lookupMsg");
  const result = document.getElementById("lookupResult");
  const { showMsg, escapeHtml } = window.PermitUI;

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    showMsg(msg, "");
    result.hidden = true;
    result.innerHTML = "";
    btn.disabled = true;
    try {
      const data = await window.PermitAPI.lookup(plateInput.value);
      if (data.found && data.permit) {
        const p = data.permit;
        showMsg(msg, "已登記車證", "ok");
        result.innerHTML = `
          <dl class="permit-dl">
            <dt>車牌</dt><dd>${escapeHtml(p.plate_number)}</dd>
            <dt>姓名</dt><dd>${escapeHtml(p.name)}</dd>
            <dt>校區</dt><dd>${escapeHtml(p.campus)}</dd>
            <dt>系級</dt><dd>${escapeHtml(p.department)}</dd>
            <dt>學號</dt><dd>${escapeHtml(p.student_id || "—")}</dd>
            <dt>備註</dt><dd>${escapeHtml(p.note || "—")}</dd>
          </dl>`;
      } else {
        showMsg(msg, `車牌 ${data.plate_number || plateInput.value} 尚無車證紀錄`, "warn");
      }
      result.hidden = false;
    } catch (err) {
      showMsg(msg, err.message || String(err), "error");
    } finally {
      btn.disabled = false;
    }
  });
})();
