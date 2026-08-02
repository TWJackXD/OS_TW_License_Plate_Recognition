/**
 * Niimbot B1 instant ticket print (58×80 mm @ 300 dpi artwork).
 * Depends on /static/vendor/niimbot.js → window.Niimbot
 *
 * Label artwork is drawn at true 58×80 mm pixels (685×945 @ 300 dpi).
 * B1 printhead is ~384 px @ 203 dpi; Bluetooth print scales to printhead size.
 */
(() => {
  const CFG = window.__NIIMBOT_CONFIG || {};
  const DENSITY = Math.max(1, Math.min(5, Number(CFG.density) || 3));
  const LABEL_TYPE = CFG.label_type != null ? Number(CFG.label_type) : 1;

  // True 58×80 mm @ 300 dpi (PDF + master artwork)
  const DPI = 300;
  const LABEL_W = 685; // 58 / 25.4 * 300 ≈ 685
  const LABEL_H = 945; // 80 / 25.4 * 300 ≈ 945

  // B1 printhead printable size @ 203 dpi
  const PRINT_W = 384;
  const PRINT_H = 640;

  const FONT = "'Noto Serif TC','Noto Sans TC','Microsoft JhengHei',serif";

  const MODEL = {
    label: "Niimbot B1",
    id: 4096,
    dpi: 203,
    protocol: "v4",
    task: "b1",
    density: DENSITY,
    label_type: LABEL_TYPE,
    speed: 1,
    name_prefixes: ["B1"],
  };

  const SIZE = { w_px: PRINT_W, h_px: PRINT_H, w_mm: 58, h_mm: 80, dpi: 203 };
  const LABEL_SIZE = { w_px: LABEL_W, h_px: LABEL_H, w_mm: 58, h_mm: 80, dpi: DPI };

  let connected = false;
  let lastPayload = null;

  function isSupported() {
    return !!(window.Niimbot && window.Niimbot.isSupported && window.Niimbot.isSupported());
  }

  function isConnected() {
    try {
      return !!(connected && window.Niimbot && window.Niimbot.printer);
    } catch {
      return false;
    }
  }

  async function connect() {
    if (!isSupported()) {
      throw new Error("此瀏覽器不支援 Web Bluetooth（請用 Chrome／Edge，且為 HTTPS 或 localhost）");
    }
    await window.Niimbot.identify(MODEL);
    connected = true;
    return window.Niimbot.printer;
  }

  async function disconnect() {
    if (window.Niimbot && window.Niimbot.disconnect) {
      await window.Niimbot.disconnect();
    }
    connected = false;
  }

  function formatTime(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString("zh-TW", { hour12: false });
    } catch {
      return String(value);
    }
  }

  function correctPlaceName(text) {
    return String(text || "").replaceAll("財經學院", "財金學院");
  }

  function formatLocation(v) {
    if (v && v.location_name) return correctPlaceName(v.location_name);
    if (v && v.latitude != null && v.longitude != null) {
      return `校區（${Number(v.latitude).toFixed(5)}, ${Number(v.longitude).toFixed(5)}）`;
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

  async function ensureFonts() {
    if (!document.fonts || !document.fonts.load) return;
    try {
      await Promise.all([
        document.fonts.load(`400 16px ${FONT}`),
        document.fonts.load(`700 24px ${FONT}`),
      ]);
      await document.fonts.ready;
    } catch {
      /* ignore */
    }
  }

  function drawCell(ctx, x, y, w, h, label, value, opts = {}) {
    const labelW = opts.labelW != null ? opts.labelW : Math.min(96, Math.floor(w * 0.32));
    ctx.strokeRect(x, y, w, h);
    // No fill background — black border only
    ctx.fillStyle = "#000000";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    const midY = y + h / 2;
    ctx.font = `bold 16px ${FONT}`;
    ctx.fillText(label, x + 7, midY);
    ctx.font = opts.valueFont || `16px ${FONT}`;
    // Single-line values stay vertically centered; long text wraps from mid-ish top
    const valueMaxW = w - labelW - 16;
    const metrics = ctx.measureText(String(value || ""));
    if (metrics.width <= valueMaxW) {
      ctx.fillText(String(value || ""), x + labelW + 8, midY);
    } else {
      ctx.textBaseline = "alphabetic";
      wrapText(ctx, value, x + labelW + 8, y + Math.floor(h * 0.38), valueMaxW, 18);
      ctx.textBaseline = "middle";
    }
  }

  function drawTicket(canvas, violation, permit) {
    const W = LABEL_W;
    const H = LABEL_H;
    const ctx = canvas.getContext("2d");
    canvas.width = W;
    canvas.height = H;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#000000";
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 2;

    const pad = 18;
    const titleMarginY = 14; // vertical margin around title block lines
    let y = pad + titleMarginY;
    const innerW = W - pad * 2;

    ctx.textAlign = "center";
    ctx.font = `bold 24px ${FONT}`;
    ctx.fillText("國立高雄科技大學", W / 2, y + 24);
    y += 24 + titleMarginY;

    ctx.font = `bold 26px ${FONT}`;
    ctx.fillText("校園車輛違規罰單", W / 2, y + 26);
    y += 26 + titleMarginY;

    ctx.font = `16px ${FONT}`;
    ctx.fillText(`單號：${docNo(violation)}`, W / 2, y + 16);
    y += 16 + titleMarginY;

    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(W - pad, y);
    ctx.stroke();
    y += 12;

    const rowH = 48;
    const fullRows = [
      ["車牌號碼", String(violation.plate_number || "—"), `bold 20px ${FONT}`],
      ["違規時間", formatTime(violation.created_at), `16px ${FONT}`],
      ["違規地點", formatLocation(violation), `16px ${FONT}`],
      ["違規事實", String(violation.reason || "—"), `16px ${FONT}`],
    ];

    for (const [label, value, valueFont] of fullRows) {
      drawCell(ctx, pad, y, innerW, rowH, label, value, { labelW: 96, valueFont });
      y += rowH;
    }

    // 從正中央對半切開；學號／系級同右欄 x，文字左對齊
    const half = Math.floor(innerW / 2);
    const name = permit && permit.name ? String(permit.name) : "（未登記車證）";
    const sid = permit && permit.student_id ? String(permit.student_id) : "—";
    drawCell(ctx, pad, y, half, rowH, "車主姓名", name, { labelW: 96 });
    drawCell(ctx, pad + half, y, innerW - half, rowH, "學號", sid, { labelW: 52 });
    y += rowH;

    const campus = permit && permit.campus ? String(permit.campus) : "—";
    const dept = permit && permit.department ? String(permit.department) : "—";
    drawCell(ctx, pad, y, half, rowH, "所屬校區", campus, { labelW: 96 });
    drawCell(ctx, pad + half, y, innerW - half, rowH, "系級", dept, { labelW: 52 });
    y += rowH + 14;

    const sectionMarginY = 12;
    ctx.textAlign = "left";
    ctx.font = `bold 17px ${FONT}`;
    y += sectionMarginY;
    ctx.fillText("裁處依據", pad, y);
    y += 20 + sectionMarginY;
    ctx.font = `14px ${FONT}`;
    y = wrapText(
      ctx,
      "依本校校園車輛管理相關規定，上開車輛有違規情事，特此舉發。",
      pad,
      y,
      innerW,
      18
    );

    y += sectionMarginY;
    ctx.font = `bold 17px ${FONT}`;
    ctx.fillText("應辦事項", pad, y);
    y += 20 + sectionMarginY;
    ctx.font = `14px ${FONT}`;
    const items = [
      "1. 請於收受本單之日起七日內辦理。",
      "2. 如有異議，請檢具證明文件提出申訴。",
      "3. 逾期未辦，得依規定加重處理。",
    ];
    for (const line of items) {
      y = wrapText(ctx, line, pad, y, innerW, 18) + 4;
    }

    y += 10;
    const printedAt = new Date().toLocaleString("zh-TW", { hour12: false });
    ctx.font = `13px ${FONT}`;
    ctx.fillText(`列印時間：${printedAt}`, pad, Math.min(y, H - 52));
    ctx.textAlign = "center";
    // Keep clear of bottom edge so thermal cut / PDF crop won't clip it
    ctx.fillText("本單由系統自動產製，請妥為保存。", W / 2, H - 36);
  }

  function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
    const chars = String(text || "");
    let line = "";
    let cy = y;
    for (let i = 0; i < chars.length; i++) {
      const test = line + chars[i];
      if (ctx.measureText(test).width > maxWidth && line) {
        ctx.fillText(line, x, cy);
        line = chars[i];
        cy += lineHeight;
      } else {
        line = test;
      }
    }
    if (line) ctx.fillText(line, x, cy);
    return cy + lineHeight;
  }

  async function canvasToPngUrl(canvas) {
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("無法產生罰單圖像"))), "image/png");
    });
    return URL.createObjectURL(blob);
  }

  /** Scale master 58×80 artwork to B1 printhead size. */
  function scaleForPrinthead(src) {
    const out = document.createElement("canvas");
    out.width = PRINT_W;
    out.height = PRINT_H;
    const ctx = out.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, PRINT_W, PRINT_H);
    ctx.drawImage(src, 0, 0, PRINT_W, PRINT_H);
    return out;
  }

  /** Render true 58×80 mm @ 300 dpi ticket canvas (685×945) — use for PDF. */
  function renderTicketCanvas(violation, permit) {
    const canvas = document.createElement("canvas");
    drawTicket(canvas, violation || {}, permit || null);
    return canvas;
  }

  async function printTicket({ violation, permit }) {
    if (!isSupported()) {
      throw new Error("此瀏覽器不支援 Web Bluetooth");
    }
    lastPayload = { violation, permit };
    if (!isConnected()) {
      await connect();
    }

    await ensureFonts();
    const master = renderTicketCanvas(violation, permit);
    const printCanvas = scaleForPrinthead(master);
    const url = await canvasToPngUrl(printCanvas);
    try {
      await window.Niimbot.printImage(url, {
        model: MODEL,
        size: SIZE,
        copies: 1,
      });
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function retryLast() {
    if (!lastPayload) throw new Error("尚無可重試的罰單");
    return printTicket(lastPayload);
  }

  window.NiimbotPrint = {
    isSupported,
    isConnected,
    connect,
    disconnect,
    ensureFonts,
    renderTicketCanvas,
    printTicket,
    retryLast,
    size: LABEL_SIZE,
    printSize: SIZE,
    get lastPayload() {
      return lastPayload;
    },
    setLastPayload(payload) {
      lastPayload = payload;
    },
  };
})();
