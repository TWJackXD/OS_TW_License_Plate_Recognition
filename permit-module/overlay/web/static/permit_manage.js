(() => {
  const form = document.getElementById("permitForm");
  const formTitle = document.getElementById("formTitle");
  const saveBtn = document.getElementById("saveBtn");
  const cancelBtn = document.getElementById("cancelEditBtn");
  const msg = document.getElementById("manageMsg");
  const table = document.getElementById("permitTable");
  const tbody = document.getElementById("permitTableBody");
  const empty = document.getElementById("permitEmpty");
  const count = document.getElementById("permitCount");
  const { showMsg, escapeHtml } = window.PermitUI;

  let editingId = null;

  function fields() {
    return {
      plate_number: document.getElementById("plate_number").value.trim(),
      name: document.getElementById("name").value.trim(),
      campus: document.getElementById("campus").value.trim(),
      department: document.getElementById("department").value.trim(),
      student_id: document.getElementById("student_id").value.trim() || null,
      note: document.getElementById("note").value.trim() || null,
    };
  }

  function setCampusValue(value) {
    const sel = document.getElementById("campus");
    const v = (value || "").trim();
    if (!v) {
      sel.value = "";
      return;
    }
    const exists = [...sel.options].some((o) => o.value === v);
    if (!exists) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    }
    sel.value = v;
  }

  function resetForm() {
    editingId = null;
    form.reset();
    const campus = document.getElementById("campus");
    campus.selectedIndex = 0;
    formTitle.textContent = "新增車證";
    saveBtn.textContent = "新增";
    cancelBtn.hidden = true;
  }

  function startEdit(item) {
    editingId = item.id;
    document.getElementById("plate_number").value = item.plate_number || "";
    document.getElementById("name").value = item.name || "";
    setCampusValue(item.campus);
    document.getElementById("department").value = item.department || "";
    document.getElementById("student_id").value = item.student_id || "";
    document.getElementById("note").value = item.note || "";
    formTitle.textContent = "編輯車證";
    saveBtn.textContent = "更新";
    cancelBtn.hidden = false;
    showMsg(msg, "");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function render(items) {
    count.textContent = `共 ${items.length} 筆`;
    if (!items.length) {
      table.hidden = true;
      empty.hidden = false;
      empty.textContent = "尚無車證，請先新增。";
      return;
    }
    empty.hidden = true;
    table.hidden = false;
    tbody.innerHTML = items
      .map(
        (item) => `
      <tr data-id="${item.id}">
        <td>${escapeHtml(item.plate_number)}</td>
        <td>${escapeHtml(item.name)}</td>
        <td>${escapeHtml(item.campus)}</td>
        <td>${escapeHtml(item.department)}</td>
        <td>${escapeHtml(item.student_id || "—")}</td>
        <td class="permit-table__actions">
          <button type="button" class="md-btn md-btn--tonal btn-edit">編輯</button>
          <button type="button" class="md-btn md-btn--danger btn-del">刪除</button>
        </td>
      </tr>`
      )
      .join("");

    tbody.querySelectorAll("tr").forEach((tr, idx) => {
      const item = items[idx];
      tr.querySelector(".btn-edit").addEventListener("click", () => startEdit(item));
      tr.querySelector(".btn-del").addEventListener("click", async () => {
        if (!confirm(`確定刪除車牌 ${item.plate_number} 的車證？`)) return;
        try {
          await window.PermitAPI.remove(item.id);
          if (editingId === item.id) resetForm();
          await load();
        } catch (err) {
          showMsg(msg, err.message || String(err), "error");
        }
      });
    });
  }

  async function load() {
    const data = await window.PermitAPI.list();
    render(data.items || []);
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    saveBtn.disabled = true;
    showMsg(msg, "");
    try {
      const payload = fields();
      if (editingId) {
        await window.PermitAPI.update(editingId, payload);
        showMsg(msg, "已更新車證", "ok");
      } else {
        await window.PermitAPI.create(payload);
        showMsg(msg, "已新增車證", "ok");
      }
      resetForm();
      await load();
    } catch (err) {
      showMsg(msg, err.message || String(err), "error");
    } finally {
      saveBtn.disabled = false;
    }
  });

  cancelBtn.addEventListener("click", () => {
    resetForm();
    showMsg(msg, "");
  });

  load().catch((err) => {
    empty.hidden = false;
    empty.textContent = `載入失敗：${err.message || err}`;
    showMsg(msg, err.message || String(err), "error");
  });
})();
