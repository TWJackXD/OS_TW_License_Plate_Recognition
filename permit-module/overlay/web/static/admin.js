(() => {
  const list = document.getElementById("recordsList");
  const mapHint = document.getElementById("mapHint");
  const recordCount = document.getElementById("recordCount");

  const map = L.map("map").setView([22.7555, 120.3332], 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  const markers = L.layerGroup().addTo(map);
  const campusLayer = L.geoJSON(null, {
    style: () => ({
      color: "#b42318",
      weight: 2.5,
      dashArray: "6 4",
      fillColor: "#f97066",
      fillOpacity: 0.08,
    }),
    onEachFeature: (feature, layer) => {
      const name = feature.properties?.name || "校區";
      layer.bindPopup(`<strong>${escapeHtml(name)}</strong><br/>舉發範圍`);
      layer.bindTooltip(name, { sticky: true, direction: "center", opacity: 0.9 });
    },
  }).addTo(map);

  let items = [];
  let campusLoaded = false;

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function focusItem(item, el) {
    document.querySelectorAll(".md-list-item.is-active").forEach((node) => {
      node.classList.remove("is-active");
    });
    if (el) el.classList.add("is-active");

    if (item.latitude != null && item.longitude != null) {
      map.setView([item.latitude, item.longitude], 18);
      const place = item.location_name ? `${item.location_name} · ` : "";
      mapHint.textContent = `${item.plate_number} · ${place}${item.created_at} · ${item.reason}`;
    } else {
      mapHint.textContent = "此筆紀錄沒有 GPS 座標。";
    }
  }

  function renderList() {
    if (!items.length) {
      list.innerHTML = `<div class="md-empty">尚無紀錄，先到「回報」拍照送出</div>`;
      recordCount.textContent = "";
      return;
    }

    recordCount.textContent = `${items.length} 筆`;
    list.innerHTML = items
      .map((item) => {
        const thumb = item.boxed_url || item.original_url || "";
        const place =
          item.location_name ||
          (item.latitude != null
            ? `${Number(item.latitude).toFixed(4)}, ${Number(item.longitude).toFixed(4)}`
            : "無 GPS");
        const support = [item.created_at, item.reason, place].join(" · ");
        return `
          <div class="md-list-item-row" data-id="${item.id}">
            <button type="button" class="md-list-item" data-id="${item.id}">
              ${
                thumb
                  ? `<img class="md-list-item__thumb" src="${escapeHtml(thumb)}" alt="" />`
                  : `<div class="md-list-item__thumb"></div>`
              }
              <div>
                <p class="md-list-item__title">${escapeHtml(item.plate_number)}</p>
                <p class="md-list-item__support">${escapeHtml(support)}</p>
              </div>
            </button>
            <button type="button" class="md-btn md-btn--danger md-list-item__delete" data-delete-id="${item.id}">
              刪除
            </button>
          </div>`;
      })
      .join("");

    list.querySelectorAll(".md-list-item").forEach((el) => {
      el.addEventListener("click", () => {
        const item = items.find((x) => String(x.id) === el.dataset.id);
        if (item) focusItem(item, el);
      });
    });

    list.querySelectorAll("[data-delete-id]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const id = Number(el.getAttribute("data-delete-id"));
        deleteItem(id);
      });
    });
  }

  async function deleteItem(id) {
    const item = items.find((x) => x.id === id);
    if (!item) return;
    if (!confirm(`確定刪除車牌 ${item.plate_number}（#${id}）？`)) return;
    try {
      const res = await fetch(`/api/violations/${id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "刪除失敗");
      }
      items = items.filter((x) => x.id !== id);
      renderList();
      renderMarkers();
      mapHint.textContent = `已刪除 #${id} ${item.plate_number}`;
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  function renderMarkers() {
    markers.clearLayers();
    const withGps = items.filter((x) => x.latitude != null && x.longitude != null);
    withGps.forEach((item) => {
      const label = item.location_name
        ? `${escapeHtml(item.plate_number)}<br/>${escapeHtml(item.location_name)}`
        : escapeHtml(item.plate_number);
      const marker = L.marker([item.latitude, item.longitude]).bindPopup(
        `<strong>${label}</strong><br/>${escapeHtml(item.reason)}<br/>${escapeHtml(item.created_at)}`
      );
      marker.on("click", () => {
        const el = list.querySelector(`.md-list-item[data-id="${item.id}"]`);
        focusItem(item, el);
      });
      markers.addLayer(marker);
    });
    if (withGps.length) {
      const group = L.featureGroup(withGps.map((i) => L.marker([i.latitude, i.longitude])));
      map.fitBounds(group.getBounds().pad(0.25));
    }
    setTimeout(() => map.invalidateSize(), 200);
  }

  async function loadCampusBoundaries() {
    if (campusLoaded) return;
    try {
      const res = await fetch("/api/map/campus");
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        mapHint.textContent =
          typeof data?.detail === "string" ? data.detail : "校區範圍載入失敗";
        return;
      }
      campusLayer.clearLayers();
      campusLayer.addData(data);
      campusLoaded = true;
      const n = (data.features || []).length;
      mapHint.textContent = `已載入 ${n} 個校區舉發範圍（紅虛線）`;
      if (n && !items.some((x) => x.latitude != null)) {
        try {
          map.fitBounds(campusLayer.getBounds().pad(0.08));
        } catch (_err) {
          /* ignore empty */
        }
      }
    } catch (err) {
      mapHint.textContent = `校區範圍載入失敗：${err.message || err}`;
    }
  }

  async function load() {
    const res = await fetch("/api/violations?limit=300");
    const data = await res.json();
    items = data.items || [];
    renderList();
    renderMarkers();
  }

  async function fetchWithTimeout(url, options = {}, ms = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  async function resolveLocations() {
    const btn = document.getElementById("resolveLocBtn");
    if (btn) btn.disabled = true;
    mapHint.textContent = "正在解析校區內地點名稱…";
    try {
      const res = await fetchWithTimeout(
        "/api/violations/resolve-locations?limit=300",
        { method: "POST" },
        120000
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "解析失敗");
      }
      await load();
      const msg =
        `地點解析完成：更新 ${data.updated ?? 0} 筆，略過 ${data.skipped ?? 0} 筆` +
        (data.outside_campus ? `，校區外 ${data.outside_campus} 筆` : "");
      mapHint.textContent = msg;
      alert(msg);
    } catch (err) {
      const msg =
        err.name === "AbortError" ? "地點解析逾時，請稍後再試" : err.message || String(err);
      mapHint.textContent = msg;
      alert(msg);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  const resolveBtn = document.getElementById("resolveLocBtn");
  if (resolveBtn) resolveBtn.addEventListener("click", resolveLocations);

  Promise.all([load(), loadCampusBoundaries()]).catch((err) => {
    list.innerHTML = `<div class="md-empty">載入失敗：${escapeHtml(err.message || err)}</div>`;
  });

  setTimeout(() => map.invalidateSize(), 120);

  window.__pageCleanup = () => {
    try {
      map.remove();
    } catch (_err) {
      /* ignore */
    }
  };
})();
