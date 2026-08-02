(() => {
  const preview = document.getElementById("preview");
  const resultBoxed = document.getElementById("resultBoxed");
  const cameraFrame = document.querySelector(".md-camera-frame");
  const cameraHint = document.getElementById("cameraHint");
  const btnStartCam = document.getElementById("btnStartCam");
  const btnCapture = document.getElementById("btnCapture");
  const btnRetake = document.getElementById("btnRetake");
  const btnSubmit = document.getElementById("btnSubmit");
  const statusEl = document.getElementById("status");
  const submitStatus = document.getElementById("submitStatus");
  const gpsPill = document.getElementById("gpsPill");
  const gpsPillText = document.getElementById("gpsPillText");
  const resultCard = document.getElementById("resultCard");
  const plateInput = document.getElementById("plateInput");
  const plateDisplay = document.getElementById("plateDisplay");
  const reasonInput = document.getElementById("reasonInput");
  const metaLine = document.getElementById("metaLine");
  const usageLine = document.getElementById("usageLine");
  const fileFallback = document.getElementById("fileFallback");

  let stream = null;
  let coords = { latitude: null, longitude: null };
  let draft = null;
  let freezeUrl = null;

  function setStatus(text, type = "") {
    statusEl.textContent = text;
    statusEl.className = type;
    const chip = document.getElementById("statusChip");
    if (chip) {
      chip.classList.toggle("is-ready", type === "ok");
    }
  }

  function setSubmitStatus(text, type = "") {
    submitStatus.textContent = text;
    submitStatus.className = `md-meta ${type === "error" ? "is-error" : type === "ok" ? "is-ok" : ""}`.trim();
  }

  function updateGpsPill() {
    const icon = gpsPill.querySelector(".material-symbols-outlined");
    if (coords.latitude != null && coords.longitude != null) {
      gpsPillText.textContent = `${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`;
      gpsPill.classList.add("is-ready");
      if (icon) icon.textContent = "location_on";
    } else {
      gpsPillText.textContent = "GPS 尚未取得";
      gpsPill.classList.remove("is-ready");
      if (icon) icon.textContent = "location_off";
    }
  }

  function requestGps() {
    if (!navigator.geolocation) {
      setStatus("此裝置不支援 GPS", "error");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        coords = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
        };
        updateGpsPill();
      },
      () => {
        setStatus("無法取得 GPS，仍可拍照");
        if (window.showSnack) window.showSnack("無法取得 GPS，仍可繼續回報");
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 5000 }
    );
  }

  function revokeFreeze() {
    if (freezeUrl) {
      URL.revokeObjectURL(freezeUrl);
      freezeUrl = null;
    }
  }

  function showFrozenFrame(url) {
    revokeFreeze();
    freezeUrl = url;
    resultBoxed.src = url;
    resultBoxed.classList.remove("hidden");
    preview.classList.add("hidden");
    preview.srcObject = null;
    cameraFrame?.classList.add("is-frozen");
    cameraFrame?.classList.remove("is-live");
  }

  async function startCamera() {
    requestGps();
    revokeFreeze();
    resultBoxed.classList.add("hidden");
    resultBoxed.removeAttribute("src");
    cameraFrame?.classList.remove("is-frozen");
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 960 },
          height: { ideal: 720 },
        },
      });
      preview.srcObject = stream;
      preview.classList.remove("hidden");
      cameraFrame?.classList.add("is-live");
      if (cameraHint) cameraHint.classList.add("hidden");
      btnCapture.disabled = false;
      btnStartCam.disabled = true;
      setStatus("對準車牌後點擊快門");
    } catch (err) {
      setStatus("無法開啟相機，改用相簿");
      if (window.showSnack) window.showSnack("無法開啟相機，改用檔案上傳");
      fileFallback.classList.remove("hidden");
      fileFallback.click();
    }
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      stream = null;
    }
    preview.srcObject = null;
    btnStartCam.disabled = false;
  }

  function captureFrame() {
    const track = stream && stream.getVideoTracks()[0];
    const settings = track ? track.getSettings() : {};
    const w = settings.width || preview.videoWidth || 960;
    const h = settings.height || preview.videoHeight || 720;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(preview, 0, 0, w, h);
    return new Promise((resolve) => {
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(null);
            return;
          }
          resolve({ blob, url: URL.createObjectURL(blob) });
        },
        "image/jpeg",
        0.85
      );
    });
  }

  async function recognizeBlob(blob) {
    const form = new FormData();
    form.append("image", blob, "capture.jpg");
    if (coords.latitude != null) form.append("latitude", String(coords.latitude));
    if (coords.longitude != null) form.append("longitude", String(coords.longitude));

    const res = await fetch("/api/recognize", { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "辨識失敗");
    }
    return data;
  }

  function formatUsage(usage) {
    if (!usage) return "";
    const prompt = usage.prompt_tokens;
    const completion = usage.completion_tokens;
    const total = usage.total_tokens;
    const parts = [];
    if (prompt != null || completion != null || total != null) {
      parts.push(
        `Tokens 輸入 ${prompt ?? "—"} · 輸出 ${completion ?? "—"} · 合計 ${total ?? "—"}`
      );
    }
    if (usage.cost_usd != null && Number(usage.cost_usd) > 0) {
      const usd = Number(usage.cost_usd);
      const ntd = usd * 32;
      parts.push(`約 US$${usd.toFixed(6)}（≈ NT$${ntd.toFixed(4)}）`);
    }
    return parts.join(" · ");
  }

  function showResult(data) {
    draft = data;
    resultCard.classList.remove("hidden");
    const plate = data.plate_number || "";
    plateInput.value = plate;
    plateDisplay.textContent = plate || "（未辨識，請手動輸入）";
    metaLine.textContent = [
      data.ok ? "自動辨識成功" : `自動辨識未完成：${data.error || "未知"}`,
      coords.latitude != null
        ? `GPS ${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)}`
        : "無 GPS",
    ].join(" · ");

    const usageText = formatUsage(data.usage);
    if (usageLine) {
      if (usageText) {
        usageLine.hidden = false;
        usageLine.textContent = usageText;
      } else {
        usageLine.hidden = true;
        usageLine.textContent = "";
      }
    }

    if (data.boxed_url) {
      resultBoxed.src = data.boxed_url;
      resultBoxed.classList.remove("hidden");
      preview.classList.add("hidden");
    }
    setStatus(data.ok ? "請確認號碼並填寫原因" : data.error || "請手動輸入車牌", data.ok ? "ok" : "error");
    resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function onCapture() {
    try {
      requestGps();
      btnCapture.disabled = true;
      const frame = await captureFrame();
      if (!frame) throw new Error("無法擷取畫面");

      showFrozenFrame(frame.url);
      stopCamera();
      setStatus("畫面已定格，辨識中…");

      const data = await recognizeBlob(frame.blob);
      showResult(data);
    } catch (err) {
      setStatus(err.message || String(err), "error");
      btnCapture.disabled = false;
      if (window.showSnack) window.showSnack(err.message || String(err));
    }
  }

  async function onFileSelected(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    try {
      requestGps();
      btnCapture.disabled = true;
      const url = URL.createObjectURL(file);
      showFrozenFrame(url);
      stopCamera();
      setStatus("畫面已定格，辨識中…");
      const data = await recognizeBlob(file);
      showResult(data);
    } catch (err) {
      setStatus(err.message || String(err), "error");
      btnCapture.disabled = false;
    }
  }

  function onRetake() {
    draft = null;
    resultCard.classList.add("hidden");
    plateInput.value = "";
    reasonInput.value = "";
    setSubmitStatus("");
    revokeFreeze();
    resultBoxed.classList.add("hidden");
    resultBoxed.removeAttribute("src");
    if (cameraHint) cameraHint.classList.remove("hidden");
    cameraFrame?.classList.remove("is-frozen", "is-live");
    startCamera();
  }

  const btnConnectPrinter = document.getElementById("btnConnectPrinter");
  const btnRetryPrint = document.getElementById("btnRetryPrint");
  const printerPill = document.getElementById("printerPill");
  const printerPillText = document.getElementById("printerPillText");

  function setPrinterPill(text, ready) {
    if (!printerPillText) return;
    printerPillText.textContent = text;
    if (printerPill) printerPill.classList.toggle("is-ready", !!ready);
  }

  async function lookupPermit(plate) {
    try {
      const res = await fetch(`/api/permits?plate=${encodeURIComponent(plate)}`);
      if (!res.ok) return null;
      const data = await res.json();
      return data.found ? data.permit : null;
    } catch {
      return null;
    }
  }

  async function printAfterSubmit(violation) {
    if (!window.NiimbotPrint) return;
    const retryBtn = btnRetryPrint;
    if (retryBtn) retryBtn.hidden = true;
    setSubmitStatus(`已建立紀錄 #${violation.id}，列印中…`);
    setPrinterPill("列印中…", false);
    try {
      const permit = await lookupPermit(violation.plate_number);
      window.NiimbotPrint.setLastPayload({ violation, permit });
      await window.NiimbotPrint.printTicket({ violation, permit });
      setSubmitStatus(`已建立紀錄 #${violation.id}，罰單已送出列印`, "ok");
      setPrinterPill("已連線 · 列印完成", true);
      if (window.showSnack) window.showSnack("罰單已列印");
    } catch (err) {
      const msg = err.message || String(err);
      setSubmitStatus(`已建立紀錄 #${violation.id}（列印失敗：${msg}）`, "error");
      setPrinterPill("列印失敗", false);
      if (retryBtn) retryBtn.hidden = false;
    }
  }

  async function onSubmit() {
    if (!draft) {
      setSubmitStatus("尚無辨識結果可送出。", "error");
      return;
    }
    const plate = plateInput.value.trim();
    const reason = reasonInput.value.trim();
    if (!plate) {
      setSubmitStatus("請填寫車牌號碼。", "error");
      return;
    }
    if (!reason) {
      setSubmitStatus("請填寫違規原因。", "error");
      return;
    }

    btnSubmit.disabled = true;
    setSubmitStatus("送出中…");
    try {
      const res = await fetch("/api/violations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plate_number: plate,
          reason,
          latitude: draft.latitude ?? coords.latitude,
          longitude: draft.longitude ?? coords.longitude,
          original_path: draft.original_path,
          boxed_path: draft.boxed_path,
          processed_path: draft.processed_path,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "送出失敗");
      const violation = {
        id: data.id,
        plate_number: plate,
        reason,
        created_at: new Date().toISOString(),
        latitude: draft.latitude ?? coords.latitude,
        longitude: draft.longitude ?? coords.longitude,
        location_name: data.location_name || null,
      };
      const msg = `已建立紀錄 #${data.id}`;
      setSubmitStatus(msg, "ok");
      if (window.showSnack) window.showSnack(msg);
      if (window.NiimbotPrint) {
        await printAfterSubmit(violation);
      }
      btnSubmit.disabled = false;
    } catch (err) {
      setSubmitStatus(err.message || String(err), "error");
      btnSubmit.disabled = false;
    }
  }

  plateInput.addEventListener("input", () => {
    plateDisplay.textContent = plateInput.value.trim() || "—";
  });

  btnStartCam.addEventListener("click", startCamera);
  btnCapture.addEventListener("click", onCapture);
  btnRetake.addEventListener("click", onRetake);
  btnSubmit.addEventListener("click", onSubmit);
  fileFallback.addEventListener("change", onFileSelected);

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
        if (window.showSnack) window.showSnack("印表機已連接");
      } catch (err) {
        setPrinterPill("連接失敗", false);
        setStatus(err.message || String(err), "error");
        if (window.showSnack) window.showSnack(err.message || String(err));
      } finally {
        btnConnectPrinter.disabled = false;
      }
    });
    if (window.NiimbotPrint && !window.NiimbotPrint.isSupported()) {
      setPrinterPill("瀏覽器不支援 Bluetooth", false);
      btnConnectPrinter.disabled = true;
    }
  }

  if (btnRetryPrint) {
    btnRetryPrint.addEventListener("click", async () => {
      if (!window.NiimbotPrint) return;
      btnRetryPrint.disabled = true;
      setSubmitStatus("重新列印中…");
      try {
        await window.NiimbotPrint.retryLast();
        setSubmitStatus("罰單已重新列印", "ok");
        setPrinterPill("已連線 · 列印完成", true);
        btnRetryPrint.hidden = true;
      } catch (err) {
        setSubmitStatus(`列印失敗：${err.message || err}`, "error");
        setPrinterPill("列印失敗", false);
      } finally {
        btnRetryPrint.disabled = false;
      }
    });
  }

  requestGps();

  window.__pageCleanup = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    if (freezeUrl) {
      URL.revokeObjectURL(freezeUrl);
      freezeUrl = null;
    }
  };
})();
