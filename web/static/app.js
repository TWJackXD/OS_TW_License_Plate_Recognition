(() => {
  const ASSET_V = "20260801a";
  const SPA_PATHS = new Set(["/", "/admin", "/pressure"]);
  const btnInstall = document.getElementById("btnInstall");
  const snackbar = document.getElementById("snackbar");
  const snackbarText = document.getElementById("snackbarText");
  const main = document.querySelector(".md-content");
  const titleEl = document.querySelector(".md-top-app-bar__title");
  const nav = document.querySelector(".md-bottom-nav");
  let deferredPrompt = null;
  let snackTimer = null;
  let navigating = false;

  window.showSnack = function showSnack(message, ms = 3200) {
    if (!snackbar || !snackbarText) return;
    snackbarText.textContent = message;
    snackbar.hidden = false;
    clearTimeout(snackTimer);
    snackTimer = setTimeout(() => {
      snackbar.hidden = true;
    }, ms);
  };

  function playRipple(target, event) {
    if (!target) return;
    const rect = target.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 1.35;
    const ripple = document.createElement("span");
    ripple.className = "md-ripple";
    ripple.style.width = `${size}px`;
    ripple.style.height = `${size}px`;

    const x = (event?.clientX ?? rect.left + rect.width / 2) - rect.left - size / 2;
    const y = (event?.clientY ?? rect.top + rect.height / 2) - rect.top - size / 2;
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    target.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
  }

  function normalizePath(pathname) {
    if (!pathname || pathname === "") return "/";
    if (pathname.length > 1 && pathname.endsWith("/")) return pathname.slice(0, -1);
    return pathname;
  }

  function updateNavActive(pathname) {
    const path = normalizePath(pathname);
    document.querySelectorAll(".md-bottom-nav__item").forEach((item) => {
      const href = item.getAttribute("href") || "";
      const itemPath = normalizePath(new URL(href, location.origin).pathname);
      item.classList.toggle("is-active", itemPath === path);
    });
  }

  function cleanupPage() {
    if (typeof window.__pageCleanup === "function") {
      try {
        window.__pageCleanup();
      } catch (_err) {
        /* ignore */
      }
    }
    window.__pageCleanup = null;

    document.querySelectorAll("video").forEach((video) => {
      if (video.srcObject) {
        video.srcObject.getTracks().forEach((track) => track.stop());
        video.srcObject = null;
      }
    });

    document.querySelectorAll("script[data-page-script]").forEach((node) => node.remove());
    document.querySelectorAll('link[data-page-style="leaflet"]').forEach((node) => node.remove());
  }

  function ensureLeafletCss() {
    if (document.querySelector('link[data-page-style="leaflet"]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    link.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
    link.crossOrigin = "";
    link.dataset.pageStyle = "leaflet";
    document.head.appendChild(link);
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[data-page-script][src="${src}"]`);
      if (existing) {
        existing.remove();
      }
      const script = document.createElement("script");
      script.src = src;
      script.async = false;
      script.dataset.pageScript = "1";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`無法載入 ${src}`));
      document.body.appendChild(script);
    });
  }

  async function runPageScripts(doc) {
    const path = normalizePath(location.pathname);
    if (path === "/admin") {
      ensureLeafletCss();
      if (!window.L) {
        await loadScript("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
      }
      await loadScript(`/static/admin.js?v=${ASSET_V}`);
      return;
    }
    if (path === "/pressure") {
      await loadScript(`/static/pressure.js?v=${ASSET_V}`);
      return;
    }
    if (path === "/") {
      await loadScript(`/static/capture.js?v=${ASSET_V}`);
    }
  }

  async function navigate(url, { push = true } = {}) {
    const next = new URL(url, location.origin);
    const path = normalizePath(next.pathname);
    if (!SPA_PATHS.has(path) || !main) {
      location.href = next.href;
      return;
    }
    if (normalizePath(location.pathname) === path && push) {
      updateNavActive(path);
      return;
    }
    if (navigating) return;
    navigating = true;
    main.classList.add("is-swapping");

    try {
      const res = await fetch(next.pathname + next.search, {
        credentials: "same-origin",
        headers: { Accept: "text/html", "X-Requested-With": "spa" },
      });
      if (!res.ok) throw new Error(`頁面載入失敗（${res.status}）`);
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const nextMain = doc.querySelector(".md-content");
      const nextTitle = doc.querySelector(".md-top-app-bar__title");
      if (!nextMain) throw new Error("頁面內容格式錯誤");

      cleanupPage();
      document.body.className = doc.body.className || "";
      document.title = doc.title || document.title;
      if (titleEl && nextTitle) titleEl.textContent = nextTitle.textContent;
      main.innerHTML = nextMain.innerHTML;

      if (push) history.pushState({ spa: true }, "", next.pathname + next.search);
      updateNavActive(path);
      window.scrollTo(0, 0);

      await runPageScripts(doc);
    } catch (err) {
      if (window.showSnack) window.showSnack(err.message || "換頁失敗");
      else alert(err.message || "換頁失敗");
    } finally {
      main.classList.remove("is-swapping");
      navigating = false;
    }
  }

  if (nav) {
    nav.addEventListener("pointerdown", (event) => {
      const item = event.target.closest(".md-bottom-nav__item");
      if (!item || !nav.contains(item)) return;
      playRipple(item, event);
    });

    nav.addEventListener("click", (event) => {
      const item = event.target.closest(".md-bottom-nav__item");
      if (!item || !nav.contains(item)) return;
      const href = item.getAttribute("href");
      if (!href) return;
      const url = new URL(href, location.origin);
      if (!SPA_PATHS.has(normalizePath(url.pathname))) return;
      event.preventDefault();
      navigate(url.pathname);
    });
  }

  window.addEventListener("popstate", () => {
    navigate(location.pathname + location.search, { push: false });
  });

  updateNavActive(location.pathname);

  if ("serviceWorker" in navigator) {
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });

    window.addEventListener("load", async () => {
      try {
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map((r) => r.update().catch(() => undefined)));

        const reg = await navigator.serviceWorker.register(`/sw.js?v=${ASSET_V}`, {
          scope: "/",
          updateViaCache: "none",
        });

        if (reg.waiting) {
          reg.waiting.postMessage({ type: "SKIP_WAITING" });
        }

        reg.addEventListener("updatefound", () => {
          const worker = reg.installing;
          if (!worker) return;
          worker.addEventListener("statechange", () => {
            if (worker.state === "installed" && navigator.serviceWorker.controller) {
              worker.postMessage({ type: "SKIP_WAITING" });
            }
          });
        });
      } catch (_err) {
        /* ignore */
      }
    });
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (btnInstall) btnInstall.hidden = false;
  });

  if (btnInstall) {
    btnInstall.addEventListener("click", async (event) => {
      playRipple(btnInstall, event);
      if (!deferredPrompt) {
        window.showSnack("若已安裝，可從主畫面開啟此 App");
        return;
      }
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
      btnInstall.hidden = true;
    });
  }
})();
