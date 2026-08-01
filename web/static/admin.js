(() => {
  const list = document.getElementById("recordsList");
  const mapHint = document.getElementById("mapHint");
  const recordCount = document.getElementById("recordCount");

  const map = L.map("map").setView([23.9739, 120.982], 7);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  const markers = L.layerGroup().addTo(map);
  let items = [];

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
      map.setView([item.latitude, item.longitude], 16);
      mapHint.textContent = `${item.plate_number} · ${item.created_at} · ${item.reason}`;
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
        const support = [
          item.created_at,
          item.reason,
          item.latitude != null
            ? `${Number(item.latitude).toFixed(4)}, ${Number(item.longitude).toFixed(4)}`
            : "無 GPS",
        ].join(" · ");
        return `
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
          </button>`;
      })
      .join("");

    list.querySelectorAll(".md-list-item").forEach((el) => {
      el.addEventListener("click", () => {
        const item = items.find((x) => String(x.id) === el.dataset.id);
        if (item) focusItem(item, el);
      });
    });
  }

  function renderMarkers() {
    markers.clearLayers();
    const withGps = items.filter((x) => x.latitude != null && x.longitude != null);
    withGps.forEach((item) => {
      const marker = L.marker([item.latitude, item.longitude]).bindPopup(
        `<strong>${escapeHtml(item.plate_number)}</strong><br/>${escapeHtml(item.reason)}<br/>${escapeHtml(item.created_at)}`
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

  async function load() {
    const res = await fetch("/api/violations?limit=300");
    const data = await res.json();
    items = data.items || [];
    renderList();
    renderMarkers();
  }

  load().catch((err) => {
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
