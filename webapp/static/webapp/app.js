/* ============================================================
   ABB Workforce360 — Application Logic v2
   ============================================================ */
(() => {
  "use strict";

  /* ---- Helpers ---- */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const csrf = () =>
    $('meta[name="csrf-token"]')?.content ||
    $('input[name="csrfmiddlewaretoken"]')?.value || "";

  async function api(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("X-CSRFToken", csrf());
    if (options.body && !(options.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    const res = await fetch(url, { ...options, headers, credentials: "same-origin" });
    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      try { const d = await res.json(); msg = d.detail || d.message || msg; } catch {}
      throw new Error(msg);
    }
    return res.status === 204 ? null : res.json().catch(() => null);
  }

  const fmt = v => v ? new Date(v).toLocaleString() : "—";
  const fmtTime = v => v ? new Date(v).toLocaleTimeString() : "—";

  function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
  }

  /* ---- Confirmation dialog ---- */
  function confirmAction(title, message, confirmLabel, onConfirm) {
    const overlay = document.createElement("div");
    overlay.className = "confirm-overlay";
    overlay.innerHTML = `<div class="confirm-dialog">
      <h3>${title}</h3>
      <p>${message}</p>
      <div class="confirm-actions">
        <button class="btn btn-secondary" data-action="cancel">Cancel</button>
        <button class="btn btn-danger" data-action="confirm">${confirmLabel}</button>
      </div>
    </div>`;
    document.body.append(overlay);
    overlay.querySelector('[data-action="cancel"]').addEventListener("click", () => overlay.remove());
    overlay.querySelector('[data-action="confirm"]').addEventListener("click", () => {
      overlay.remove(); onConfirm();
    });
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  }

  /* ---- Button loading spinner ---- */
  function btnLoad(btn, loading) {
    if (!btn) return;
    btn.classList.toggle("loading", loading);
    btn.disabled = loading;
  }

  /* ---- Theme ---- */
  function initTheme() {
    const applyIcons = (dark) => {
      $$(".icon-sun").forEach(el => el.style.display = dark ? "none" : "block");
      $$(".icon-moon").forEach(el => el.style.display = dark ? "block" : "none");
    };
    const toggle = () => {
      const isDark = document.documentElement.dataset.theme !== "dark";
      document.documentElement.dataset.theme = isDark ? "dark" : "";
      try { localStorage.setItem("wf-theme", isDark ? "dark" : ""); } catch {}
      applyIcons(isDark);
    };
    $("#theme-toggle")?.addEventListener("click", toggle);
    $("#login-theme-toggle")?.addEventListener("click", toggle);
    applyIcons(document.documentElement.dataset.theme === "dark");
  }
  initTheme();

  /* ---- Toast / Notice ---- */
  function notice(message, isError = false) {
    const box = $("#notice");
    if (!box) return;
    box.innerHTML = "";
    box.className = `toast ${isError ? "error" : "success"}`;
    // Icon
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 20 20"); svg.setAttribute("fill", "currentColor");
    svg.setAttribute("width", "18"); svg.setAttribute("height", "18");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    if (isError) {
      path.setAttribute("fill-rule", "evenodd"); path.setAttribute("clip-rule", "evenodd");
      path.setAttribute("d", "M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z");
    } else {
      path.setAttribute("fill-rule", "evenodd"); path.setAttribute("clip-rule", "evenodd");
      path.setAttribute("d", "M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z");
    }
    svg.appendChild(path);
    const txt = document.createElement("span"); txt.textContent = message;
    const closeBtn = document.createElement("button");
    closeBtn.className = "toast-close"; closeBtn.innerHTML = "✕"; closeBtn.title = "Dismiss";
    closeBtn.addEventListener("click", () => { box.hidden = true; });
    box.append(svg, txt, closeBtn);
    box.hidden = false;
    clearTimeout(notice._t);
    notice._t = setTimeout(() => { box.hidden = true; }, 6000);
  }

  /* ---- Audio feedback for scanners ---- */
  function beep(accepted) {
    try {
      const C = window.AudioContext || window.webkitAudioContext;
      if (!C) return;
      const ctx = new C(), osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.type = accepted ? "sine" : "sawtooth";
      osc.frequency.value = accepted ? 660 : 190;
      gain.gain.value = 0.12; osc.start(); osc.stop(ctx.currentTime + 0.2);
      osc.onended = () => ctx.close();
    } catch {}
  }

  /* ---- DOM builders ---- */
  function cell(row, value, cls = "") {
    const td = document.createElement("td");
    td.textContent = value ?? "—";
    if (cls) td.className = cls;
    row.append(td);
    return td;
  }
  function mkButton(label, cls, action) {
    const b = document.createElement("button");
    b.type = "button"; b.className = cls; b.textContent = label;
    b.addEventListener("click", action);
    return b;
  }
  function downloadPdf(url, filename) {
    fetch(url, { credentials: "same-origin" })
      .then(r => {
        const cd = r.headers.get("Content-Disposition") || "";
        if (!filename) {
          const m = cd.match(/filename="?([^";\n]+)"?/i);
          filename = m ? m[1] : "document.pdf";
        }
        if (!filename.endsWith(".pdf")) filename += ".pdf";
        return r.blob().then(blob => ({ blob, filename }));
      })
      .then(({ blob, filename }) => {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl; a.download = filename; a.style.display = "none";
        document.body.append(a); a.click();
        setTimeout(() => { a.remove(); URL.revokeObjectURL(blobUrl); }, 200);
      })
      .catch(() => notice("PDF download failed", true));
  }
  function mkLink(label, href) {
    const btn = document.createElement("button");
    btn.type = "button"; btn.textContent = label;
    btn.className = "btn btn-secondary btn-xs";
    btn.addEventListener("click", () => downloadPdf(href));
    return btn;
  }
  function setRows(sel, rows) {
    const t = $(sel);
    if (t) { t.replaceChildren(); rows.forEach(r => t.append(r)); }
  }
  function makeBadge(text, type) {
    const span = document.createElement("span");
    span.className = `badge badge-${type}`;
    span.textContent = text;
    return span;
  }
  function makeStatCard(label, value, colorClass = "") {
    const d = document.createElement("div"); d.className = "stat-card";
    const s = document.createElement("span"); s.className = "stat-label"; s.textContent = label;
    const b = document.createElement("span"); b.className = `stat-value ${colorClass}`; b.textContent = value;
    d.append(s, b);
    return d;
  }

  /* ---- Login ---- */
  const loginForm = $("#login-form");
  if (loginForm && !$(".shell")) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errBox = $("#login-error"), errSpan = errBox?.querySelector("span");
      const submitBtn = $("#login-submit");
      errBox?.classList.remove("visible");
      btnLoad(submitBtn, true);
      try {
        const data = Object.fromEntries(new FormData(loginForm));
        await api("/api/auth/login", { method: "POST", body: JSON.stringify(data) });
        location.reload();
      } catch (err) {
        if (errSpan) errSpan.textContent = err.message;
        errBox?.classList.add("visible");
      } finally {
        btnLoad(submitBtn, false);
      }
    });
    return; // Stop here — login page only
  }

  /* ================================================================
     Application Shell (authenticated)
     ================================================================ */

  /* ---- Sidebar mobile toggle ---- */
  const sidebar = $("#sidebar"), overlay = $("#sidebar-overlay");
  const openSidebar = () => { sidebar?.classList.add("open"); overlay?.classList.add("active"); };
  const closeSidebar = () => { sidebar?.classList.remove("open"); overlay?.classList.remove("active"); };
  $("#mobile-toggle")?.addEventListener("click", openSidebar);
  overlay?.addEventListener("click", closeSidebar);

  /* ---- Registration panel toggles ---- */
  $("#toggle-worker-register")?.addEventListener("click", () => {
    const panel = $("#worker-register-panel");
    if (panel) { panel.hidden = !panel.hidden; if (!panel.hidden) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });
  $("#worker-register-close")?.addEventListener("click", () => {
    const panel = $("#worker-register-panel");
    if (panel) panel.hidden = true;
  });
  $("#toggle-visitor-register")?.addEventListener("click", () => {
    const panel = $("#visitor-register-panel");
    if (panel) { panel.hidden = !panel.hidden; if (!panel.hidden) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  });
  $("#visitor-register-close")?.addEventListener("click", () => {
    const panel = $("#visitor-register-panel");
    if (panel) panel.hidden = true;
  });

  /* ---- Photo Crop Modal ---- */
  const CROP_RATIO = 8 / 9; // ID card photo: 24mm x 27mm
  const CROP_OUT_W = 480;   // output px width
  const CROP_OUT_H = Math.round(CROP_OUT_W / CROP_RATIO);

  function openCropModal(imageSrc) {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.className = "camera-overlay";
      overlay.innerHTML = `<div class="camera-dialog crop-dialog">
        <div class="camera-header">
          <div><h2>Crop Photo</h2><p>Drag to reposition · Scroll or slider to zoom · Fixed ID card ratio</p></div>
          <button class="camera-close" data-action="cancel" title="Cancel">✕</button>
        </div>
        <div class="photo-crop-frame" id="crop-frame">
          <img id="crop-img" src="${imageSrc}" alt="Crop source" draggable="false">
        </div>
        <div class="crop-zoom">
          <span>−</span>
          <input type="range" id="crop-zoom" min="100" max="400" value="100" step="1">
          <span>+</span>
          <span id="crop-zoom-label" style="min-width:40px;text-align:right">100%</span>
        </div>
        <div class="camera-actions">
          <button class="btn btn-secondary" data-action="cancel">Cancel</button>
          <button class="btn btn-primary" data-action="crop">Crop &amp; Save</button>
        </div>
      </div>`;
      document.body.append(overlay);

      const frame = overlay.querySelector("#crop-frame");
      const img = overlay.querySelector("#crop-img");
      const slider = overlay.querySelector("#crop-zoom");
      const zoomLabel = overlay.querySelector("#crop-zoom-label");

      let scale = 1, offsetX = 0, offsetY = 0;
      let imgW = 0, imgH = 0;
      let dragging = false, startX = 0, startY = 0, dragOX = 0, dragOY = 0;

      function updateTransform() {
        img.style.transform = `translate(-50%, -50%) translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
      }

      img.onload = () => {
        imgW = img.naturalWidth; imgH = img.naturalHeight;
        const frameW = frame.clientWidth, frameH = frame.clientHeight;
        // Fit image to fill frame initially
        const fitScale = Math.max(frameW / imgW, frameH / imgH);
        img.style.width = imgW * fitScale + "px";
        img.style.height = imgH * fitScale + "px";
        scale = 1; offsetX = 0; offsetY = 0;
        slider.value = 100;
        zoomLabel.textContent = "100%";
        updateTransform();
      };

      function clampOffset() {
        const frameW = frame.clientWidth, frameH = frame.clientHeight;
        const dispW = img.offsetWidth * scale, dispH = img.offsetHeight * scale;
        const maxX = Math.max(0, (dispW - frameW) / 2);
        const maxY = Math.max(0, (dispH - frameH) / 2);
        offsetX = Math.max(-maxX, Math.min(maxX, offsetX));
        offsetY = Math.max(-maxY, Math.min(maxY, offsetY));
      }

      slider.addEventListener("input", () => {
        scale = parseInt(slider.value) / 100;
        zoomLabel.textContent = slider.value + "%";
        clampOffset(); updateTransform();
      });

      // Mouse wheel zoom
      frame.addEventListener("wheel", (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -5 : 5;
        const newVal = Math.max(100, Math.min(400, parseInt(slider.value) + delta));
        slider.value = newVal; scale = newVal / 100;
        zoomLabel.textContent = newVal + "%";
        clampOffset(); updateTransform();
      }, { passive: false });

      // Drag to pan
      frame.addEventListener("pointerdown", (e) => {
        dragging = true; startX = e.clientX; startY = e.clientY;
        dragOX = offsetX; dragOY = offsetY;
        frame.setPointerCapture(e.pointerId);
      });
      frame.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        offsetX = dragOX + (e.clientX - startX);
        offsetY = dragOY + (e.clientY - startY);
        clampOffset(); updateTransform();
      });
      frame.addEventListener("pointerup", () => { dragging = false; });

      function cleanup(result) {
        overlay.remove();
        resolve(result);
      }

      overlay.querySelectorAll('[data-action="cancel"]').forEach(b =>
        b.addEventListener("click", () => cleanup(null))
      );
      overlay.addEventListener("click", (e) => { if (e.target === overlay) cleanup(null); });

      overlay.querySelector('[data-action="crop"]').addEventListener("click", () => {
        const frameW = frame.clientWidth, frameH = frame.clientHeight;
        const dispW = img.offsetWidth * scale, dispH = img.offsetHeight * scale;
        // Visible region in original image coords
        const scaleToNat = imgW / (img.offsetWidth * scale);
        const visibleLeft = (dispW / 2 - offsetX - frameW / 2) * scaleToNat;
        const visibleTop = (dispH / 2 - offsetY - frameH / 2) * scaleToNat;
        const visibleW = frameW * scaleToNat;
        const visibleH = frameH * scaleToNat;

        const canvas = document.createElement("canvas");
        canvas.width = CROP_OUT_W; canvas.height = CROP_OUT_H;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, visibleLeft, visibleTop, visibleW, visibleH, 0, 0, CROP_OUT_W, CROP_OUT_H);
        canvas.toBlob((blob) => cleanup(blob), "image/jpeg", 0.92);
      });
    });
  }

  /* ---- Photo upload with crop ---- */
  function setupPhotoUpload(fileId, previewId, btnId, cameraBtn) {
    const input = $("#" + fileId), preview = $("#" + previewId), btn = $("#" + btnId);

    async function handleFile(file) {
      if (!file) return;
      const dataUrl = await new Promise((r) => {
        const fr = new FileReader(); fr.onload = e => r(e.target.result); fr.readAsDataURL(file);
      });
      const croppedBlob = await openCropModal(dataUrl);
      if (!croppedBlob) return; // user cancelled
      // Replace the file input with the cropped blob
      const dt = new DataTransfer();
      dt.items.add(new File([croppedBlob], "photo.jpg", { type: "image/jpeg" }));
      input.files = dt.files;
      // Show preview
      if (preview) {
        preview.src = URL.createObjectURL(croppedBlob);
        preview.style.display = "block";
      }
    }

    btn?.addEventListener("click", () => input?.click());
    input?.addEventListener("change", () => handleFile(input.files?.[0]));

    // Camera button support
    const camBtn = cameraBtn ? (typeof cameraBtn === "string" ? $(cameraBtn) : cameraBtn) : null;
    if (camBtn) {
      camBtn.addEventListener("click", async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 1440 } }
          });
          // Create camera overlay
          const camOverlay = document.createElement("div");
          camOverlay.className = "camera-overlay";
          camOverlay.innerHTML = `<div class="camera-dialog">
            <div class="camera-header">
              <div><h2>Take Photo</h2><p>Position the subject, then capture.</p></div>
              <button class="camera-close" data-action="cancel" title="Close">✕</button>
            </div>
            <div class="camera-view"><video autoplay playsinline muted></video></div>
            <div class="camera-actions">
              <button class="btn btn-secondary" data-action="cancel">Cancel</button>
              <button class="btn btn-primary" data-action="capture">📸 Capture</button>
            </div>
          </div>`;
          document.body.append(camOverlay);
          const video = camOverlay.querySelector("video");
          video.srcObject = stream;
          await video.play();

          const closeCamera = () => {
            stream.getTracks().forEach(t => t.stop());
            camOverlay.remove();
          };
          camOverlay.querySelectorAll('[data-action="cancel"]').forEach(b =>
            b.addEventListener("click", closeCamera)
          );
          camOverlay.addEventListener("click", (e) => { if (e.target === camOverlay) closeCamera(); });

          camOverlay.querySelector('[data-action="capture"]').addEventListener("click", async () => {
            const canvas = document.createElement("canvas");
            canvas.width = video.videoWidth; canvas.height = video.videoHeight;
            canvas.getContext("2d").drawImage(video, 0, 0);
            closeCamera();
            const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
            const croppedBlob = await openCropModal(dataUrl);
            if (!croppedBlob) return;
            const dt = new DataTransfer();
            dt.items.add(new File([croppedBlob], "photo.jpg", { type: "image/jpeg" }));
            input.files = dt.files;
            if (preview) {
              preview.src = URL.createObjectURL(croppedBlob);
              preview.style.display = "block";
            }
          });
        } catch (err) {
          notice("Camera not available: " + err.message, true);
        }
      });
    }
  }
  setupPhotoUpload("wf-photo", "wf-photo-preview", "wf-upload-btn", '[data-camera="worker-form"]');
  setupPhotoUpload("vf-photo", "vf-photo-preview", "vf-upload-btn", '[data-camera="visitor-form"]');

  /* ---- Uppercase conversion helper ---- */
  function uppercaseFormData(formData) {
    const textFields = ["name", "contractor_name", "company_name", "location", "host", "purpose"];
    for (const field of textFields) {
      const val = formData.get(field);
      if (val && typeof val === "string") formData.set(field, val.toUpperCase());
    }
    return formData;
  }

  /* ---- Post-registration preview modal ---- */
  function showPreview(type, data) {
    const overlay = document.createElement("div");
    overlay.className = "preview-overlay";
    const isWorker = type === "worker";
    const photoUrl = data.photo_url || "";
    const idCardUrl = isWorker
      ? `/api/workers/${encodeURIComponent(data.worker_id)}/id-card`
      : `/api/visitors/${encodeURIComponent(data.visitor_id)}/id-card`;
    // Auto-download the PDF immediately
    downloadPdf(idCardUrl);
    const fields = isWorker ? [
      ["Worker ID", data.worker_id], ["Worker No.", data.worker_no],
      ["Name", data.name], ["Contractor", data.contractor_name],
      ["Joining Date", data.joining_date], ["Contact", data.contact_no],
      ["Emergency Contact", data.emergency_contact], ["Aadhaar", data.aadhaar_masked],
      ["Status", data.status],
    ] : [
      ["Visitor ID", data.visitor_id], ["Pass No.", data.visitor_no],
      ["Name", data.name], ["Company", data.company_name],
      ["Location", data.location], ["Host", data.host],
      ["Purpose", data.purpose], ["Contact", data.contact_no],
      ["Aadhaar", data.aadhaar_masked], ["Expires", fmt(data.expiration_timestamp)],
      ["Status", data.status],
    ];
    const photoHtml = photoUrl
      ? `<img src="${photoUrl}" alt="${data.name}">`
      : "";
    const dlLabel = isWorker ? "Download ID Card" : "Download Pass";
    overlay.innerHTML = `<div class="preview-card">
      <div class="preview-header">
        ${photoHtml}
        <div class="preview-header-text">
          <h3>${data.name}</h3>
          <p>${isWorker ? `Worker ${data.worker_no}` : `Visitor Pass ${data.visitor_no}`} — Registered successfully</p>
        </div>
      </div>
      <div class="preview-body">
        <div class="preview-grid">
          ${fields.map(([l, v]) => `<div class="preview-field"><label>${l}</label><span>${v ?? "—"}</span></div>`).join("")}
        </div>
      </div>
      <div class="preview-footer">
        <button class="btn btn-secondary" data-action="close">Close</button>
        <button class="btn btn-primary" data-action="download">
          <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
          ${dlLabel}
        </button>
      </div>
    </div>`;
    document.body.append(overlay);
    overlay.querySelector('[data-action="close"]').addEventListener("click", () => overlay.remove());
    overlay.querySelector('[data-action="download"]').addEventListener("click", () => downloadPdf(idCardUrl));
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  }

  /* ---- Breadcrumb map ---- */
  const breadcrumbs = {
    dashboard: "ABB Plant 3 · Overview",
    workers: "ABB Plant 3 · Workforce Records",
    gate: "ABB Plant 3 · Gate Management",
    visitors: "ABB Plant 3 · Visitor Management",
    "gate-history": "ABB Plant 3 · Gate Audit",
    canteen: "ABB Plant 3 · Canteen",
    "canteen-history": "ABB Plant 3 · Canteen Reports",
  };

  /* ---- Page Navigation ---- */
  const pages = $$(".page");
  let workerPage = 1, visitorPage = 1;
  const listPageSize = 25;
  const loaders = {
    dashboard: loadDashboard, workers: loadWorkers, visitors: loadVisitors,
    "gate-history": loadGateHistory, "canteen-history": loadCanteenHistory,
    gate: loadGateRecent, canteen: loadCanteenRecent,
  };

  function openPage(name) {
    pages.forEach(p => { p.hidden = p.id !== `page-${name}`; });
    $$(".navitem").forEach(b => b.classList.toggle("active", b.dataset.page === name));
    const bc = $("#header-breadcrumb");
    if (bc) bc.textContent = breadcrumbs[name] || "ABB Plant 3";
    closeSidebar();
    try { sessionStorage.setItem("wf-page", name); } catch {}
    loaders[name]?.();
    if (name === "gate") setTimeout(() => $('#gate-form input[name="barcode"]')?.focus(), 30);
    if (name === "canteen") setTimeout(() => $('#canteen-form input[name="barcode"]')?.focus(), 30);
  }

  $$("[data-page]").forEach(b => b.addEventListener("click", () => openPage(b.dataset.page)));
  $$("[data-refresh]").forEach(b => b.addEventListener("click", () => loaders[b.dataset.refresh]?.()));
  $("#logout")?.addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } finally { location.href = "/"; }
  });
  $("#worker-search")?.addEventListener("input", debounce(() => { workerPage = 1; loadWorkers(); }, 250));
  $("#visitor-search")?.addEventListener("input", debounce(() => { visitorPage = 1; loadVisitors(); }, 250));
  $("#visitor-status")?.addEventListener("change", () => { visitorPage = 1; loadVisitors(); });
  $("#gate-date")?.addEventListener("change", loadGateHistory);
  $("#gate-result-filter")?.addEventListener("change", loadGateHistory);
  $("#canteen-date")?.addEventListener("change", loadCanteenHistory);
  $("#canteen-result-filter")?.addEventListener("change", loadCanteenHistory);

  /* ---- Pagination builder ---- */
  function renderPagination(target, page, total, size, change) {
    const box = $(target);
    if (!box) return;
    box.replaceChildren();
    const first = total ? (page - 1) * size + 1 : 0;
    const last = Math.min(page * size, total);
    const label = document.createElement("span");
    label.textContent = `Showing ${first}–${last} of ${total}`;
    box.append(label);
    const controls = document.createElement("div");
    controls.className = "pagination-controls";
    const prev = mkButton("← Previous", "btn btn-secondary btn-xs", () => change(page - 1));
    prev.disabled = page <= 1;
    const cur = document.createElement("span");
    cur.textContent = `Page ${page}`;
    cur.style.cssText = "font-weight:600;color:var(--text-1)";
    const next = mkButton("Next →", "btn btn-secondary btn-xs", () => change(page + 1));
    next.disabled = page * size >= total;
    controls.append(prev, cur, next);
    box.append(controls);
  }

  /* ---- Barcode scanner auto-submit ---- */
  for (const formId of ["gate-form", "canteen-form"]) {
    const form = $(`#${formId}`), input = $('input[name="barcode"]', form);
    if (!input) continue;
    let times = [], timer, lastCode = "", lastAt = 0;
    input.addEventListener("keydown", (e) => {
      const now = Date.now();
      if (e.key === "Enter") { times = []; return; }
      if (e.key.length !== 1) return;
      times = times.filter(t => now - t < 1000);
      times.push(now);
      clearTimeout(timer);
      timer = setTimeout(() => {
        const value = input.value.trim();
        const span = times.length > 1 ? times.at(-1) - times[0] : Infinity;
        if (value.length >= 4 && times.length >= 4 && span < 500 &&
            !(lastCode === value && Date.now() - lastAt < 1000)) {
          lastCode = value; lastAt = Date.now(); times = [];
          form.requestSubmit();
        }
      }, 140);
    });
  }

  /* ================================================================
     Data Loaders
     ================================================================ */

  async function loadDashboard() {
    try {
      const [summary, gate, meals, gateRecent, canteenRecent] = await Promise.all([
        api("/api/summary"), api("/api/gate/report"), api("/api/canteen/report"),
        api("/api/gate/transactions?page=1&page_size=100"),
        api("/api/canteen/transactions?page=1&page_size=100"),
      ]);
      $("#dash-total").textContent = summary.total;
      $("#dash-active").textContent = summary.active;
      $("#dash-inactive").textContent = summary.inactive;
      const container = $("#daily-summary");
      container.replaceChildren(
        makeStatCard("Gate Entries", gate.accepted_entries, "green"),
        makeStatCard("Gate Exits", gate.accepted_exits, "blue"),
        makeStatCard("Meal Scans", meals.successful_scans, "orange"),
        makeStatCard("Estimated Workers Inside", gate.estimated_workers_inside, "red"),
      );
      renderDashboardRecentActivity(gateRecent.items, canteenRecent.items);
    } catch (e) { notice(e.message, true); }
  }

  async function loadWorkers() {
    try {
      const q = new URLSearchParams({ page: String(workerPage), page_size: String(listPageSize) });
      const term = $("#worker-search")?.value.trim();
      if (term) q.set("name", term);
      const data = await api(`/api/workers?${q}`);
      $("#worker-total").textContent = data.total;
      $("#worker-active").textContent = data.active;
      $("#worker-inactive").textContent = data.inactive;
      renderPagination("#worker-page", workerPage, data.total, listPageSize, (p) => { workerPage = p; loadWorkers(); });
      if (!data.items.length) {
        setRows("#worker-rows", []);
        const empty = document.createElement("tr");
        const td = document.createElement("td"); td.colSpan = 11;
        td.className = "empty-state"; td.style.padding = "40px";
        td.textContent = "No workers found.";
        empty.append(td);
        $("#worker-rows")?.append(empty);
        return;
      }
      setRows("#worker-rows", data.items.map(w => {
        const tr = document.createElement("tr");
        // Photo
        const photoTd = document.createElement("td");
        const img = document.createElement("img");
        img.className = "cell-thumb"; img.src = w.photo_url; img.alt = `${w.name}`;
        img.loading = "lazy";
        photoTd.append(img); tr.append(photoTd);
        // Fields
        cell(tr, w.worker_id, "cell-mono");
        cell(tr, w.worker_no, "cell-mono");
        cell(tr, w.name, "cell-strong");
        cell(tr, w.contractor_name);
        cell(tr, w.joining_date);
        cell(tr, w.contact_no);
        cell(tr, w.emergency_contact);
        cell(tr, w.aadhaar_masked, "cell-mono");
        // Status badge
        const statusTd = document.createElement("td");
        statusTd.append(makeBadge(w.status, w.status.toLowerCase()));
        tr.append(statusTd);
        // Actions
        const actions = document.createElement("td");
        actions.className = "cell-actions";
        actions.append(mkLink("ID Card", `/api/workers/${encodeURIComponent(w.worker_id)}/id-card`));
        actions.append(mkButton(
          w.status === "Active" ? "Deactivate" : "Activate",
          `btn btn-secondary btn-xs`,
          () => {
            const newStatus = w.status === "Active" ? "Inactive" : "Active";
            const action = async () => {
              try {
                await api(`/api/workers/${encodeURIComponent(w.worker_id)}/status`, {
                  method: "POST",
                  body: JSON.stringify({ status: newStatus }),
                });
                loadWorkers();
                notice(`Worker ${w.name} ${newStatus === "Active" ? "activated" : "deactivated"}.`);
              } catch (e) { notice(e.message, true); }
            };
            if (newStatus === "Inactive") {
              confirmAction(
                "Deactivate Worker",
                `Are you sure you want to deactivate <b>${w.name}</b> (${w.worker_no})? They will not be able to enter the plant.`,
                "Deactivate",
                action
              );
            } else {
              action();
            }
          }
        ));
        tr.append(actions);
        return tr;
      }));
    } catch (e) { notice(e.message, true); }
  }

  /* ---- Worker Registration ---- */
  $("#worker-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const submit = $('button[type="submit"]', form);
    btnLoad(submit, true);
    try {
      const fd = uppercaseFormData(new FormData(form));
      const result = await api("/api/workers", { method: "POST", body: fd });
      form.reset();
      const preview = $("#wf-photo-preview"); if (preview) preview.style.display = "none";
      $("#worker-register-panel")?.setAttribute("hidden", "");
      notice(`Worker registered — ID: ${result.worker_id}, Number: ${result.worker_no}`);
      showPreview("worker", result);
      loadWorkers();
    } catch (e) { notice(e.message, true); }
    finally { btnLoad(submit, false); }
  });

  /* ---- Gate ---- */
  async function loadGateRecent() {
    try {
      const data = await api("/api/gate/transactions?page=1&page_size=10");
      renderGateFeed("#gate-recent", data.items);
    } catch (e) { notice(e.message, true); }
  }

  async function loadGateHistory() {
    try {
      const q = new URLSearchParams({ page: "1", page_size: "100" });
      const d = $("#gate-date")?.value, r = $("#gate-result-filter")?.value;
      if (d) q.set("event_date", d);
      if (r) q.set("result", r);
      const reportQuery = new URLSearchParams();
      if (d) reportQuery.set("report_date", d);
      const [data, report] = await Promise.all([
        api(`/api/gate/transactions?${q}`),
        api(`/api/gate/report?${reportQuery}`),
      ]);
      renderGateTableRows("#gate-history-rows", data.items);
      const counts = $("#gate-history-counts");
      if (counts) counts.replaceChildren(
        makeStatCard("Entries", report.accepted_entries, "green"),
        makeStatCard("Exits", report.accepted_exits, "blue"),
        makeStatCard("Estimated Workers Inside", report.estimated_workers_inside, "red"),
      );
    } catch (e) { notice(e.message, true); }
  }

  function renderGateFeed(target, rows) {
    const container = $(target);
    if (!container) return;
    container.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "feed-empty"; empty.textContent = "No transactions yet today.";
      container.append(empty); return;
    }
    rows.forEach(t => {
      const item = document.createElement("div");
      item.className = "feed-item";
      const left = document.createElement("div");
      left.className = "feed-item-left";
      const info = document.createElement("div");
      const b = document.createElement("b"); b.textContent = t.person_id;
      const small = document.createElement("small"); small.textContent = fmtTime(t.scan_timestamp);
      info.append(b, small);
      left.append(info);
      const badge = makeBadge(
        t.validation_result === "ACCEPTED" ? (t.event_type || "OK") : "REJECTED",
        t.validation_result === "ACCEPTED" ? (t.event_type === "EXIT" ? "exit" : "entry") : "rejected"
      );
      item.append(left, badge);
      container.append(item);
    });
  }

  function renderDashboardRecentActivity(gateRows, canteenRows) {
    const body = $("#dashboard-recent-rows");
    if (!body) return;
    const activity = [
      ...gateRows.map(row => ({ ...row, source: "gate" })),
      ...canteenRows.map(row => ({ ...row, source: "canteen" })),
    ].sort((a, b) => new Date(b.scan_timestamp) - new Date(a.scan_timestamp)).slice(0, 5);
    body.replaceChildren();
    if (!activity.length) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 6; td.className = "dashboard-recent-empty"; td.textContent = "No recent activity.";
      tr.append(td); body.append(tr); return;
    }
    activity.forEach(row => {
      const tr = document.createElement("tr");
      cell(tr, fmtTime(row.scan_timestamp));
      const isCanteen = row.source === "canteen";
      const accepted = isCanteen ? row.scan_result === "ACCEPTED" : row.validation_result === "ACCEPTED";
      const eventType = isCanteen ? "MEAL" : row.event_type;
      const personType = row.person_type === "VISITOR" ? "Visitor" : "Worker";
      const activityType = isCanteen ? "Canteen Scan" : `${personType} ${eventType === "EXIT" ? "Exit" : "Entry"}`;
      const iconTd = document.createElement("td");
      const icon = document.createElement("span");
      icon.className = `dashboard-activity-icon ${isCanteen ? "meal" : eventType === "EXIT" ? "exit" : "entry"}`;
      icon.textContent = isCanteen ? "✦" : eventType === "EXIT" ? "↗" : "↙";
      icon.setAttribute("aria-label", activityType);
      iconTd.append(icon); tr.append(iconTd);
      cell(tr, activityType);
      cell(tr, row.name || "—", "cell-strong");
      cell(tr, row.person_id || row.worker_id || "—", "cell-mono");
      const status = isCanteen ? (accepted ? "Meal Taken" : "Rejected")
        : (accepted ? (eventType === "EXIT" ? "Exited" : "Entered") : "Rejected");
      const statusClass = accepted ? (isCanteen ? "meal" : eventType === "EXIT" ? "exit" : "entry") : "rejected";
      const statusTd = document.createElement("td"); statusTd.append(makeBadge(status, statusClass)); tr.append(statusTd);
      body.append(tr);
    });
  }

  function renderGateTableRows(target, rows) {
    setRows(target, rows.map(t => {
      const tr = document.createElement("tr");
      // Photo column
      const photoTd = document.createElement("td");
      if (t.photo_url) {
        const img = document.createElement("img");
        img.className = "cell-thumb"; img.src = t.photo_url; img.alt = t.name || ""; img.loading = "lazy";
        photoTd.append(img);
      } else { photoTd.textContent = "—"; }
      tr.append(photoTd);
      // Name column
      cell(tr, t.name || "—", "cell-strong");
      cell(tr, fmt(t.scan_timestamp));
      cell(tr, t.person_id, "cell-mono");
      const typeTd = document.createElement("td");
      typeTd.append(makeBadge(t.person_type, t.person_type?.toLowerCase() || "unknown"));
      tr.append(typeTd);
      cell(tr, t.event_type || "—");
      const resultTd = document.createElement("td");
      resultTd.append(makeBadge(t.validation_result, t.validation_result?.toLowerCase()));
      tr.append(resultTd);
      cell(tr, t.rejection_reason || "—");
      return tr;
    }));
  }

  /* Gate scan handler */
  $("#gate-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const barcode = new FormData(form).get("barcode");
    try {
      const result = await api("/api/gate/scan", { method: "POST", body: JSON.stringify({ barcode }) });
      renderGateResult(result);
      beep(result.accepted);
      form.reset();
      await loadGateRecent();
    } catch (e) { notice(e.message, true); }
  });

  function renderGateResult(result) {
    const box = $("#gate-result");
    if (!box) return;
    box.style.display = "block";
    box.className = "result-card";
    if (result.accepted) {
      box.classList.add(result.event_type === "EXIT" ? "result-exit" : "result-entry");
    } else {
      box.classList.add("result-rejected");
    }
    let html = `<div class="result-badge">`;
    if (result.accepted) {
      html += `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
      html += `<div><h2>${result.event_type === "EXIT" ? "Exit Accepted" : "Entry Accepted"}</h2><span>${result.reason}</span></div>`;
    } else {
      html += `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
      html += `<div><h2>Scan Rejected</h2><span>${result.reason}</span></div>`;
    }
    html += `</div>`;
    if (result.person) {
      const p = result.person;
      const photoHtml = p.photo_url
        ? `<img class="person-photo" src="${p.photo_url}" alt="${p.name}" loading="lazy">`
        : `<div class="person-photo-placeholder"><svg viewBox="0 0 20 20" fill="currentColor" width="24" height="24"><path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"/></svg></div>`;
      html += `<div class="result-person">${photoHtml}<div class="person-info">
        <div class="person-badges"><span class="badge badge-${p.person_type?.toLowerCase()}">${p.person_type}</span><span class="badge badge-${p.status?.toLowerCase()}">${p.status}</span></div>
        <h3>${p.name}</h3><div class="person-meta"><span>ID: <b>${p.person_id}</b></span>${p.detail ? `<span>${p.detail}</span>` : ""}</div>
      </div></div>`;
    }
    if (result.remaining_seconds) {
      const mins = Math.ceil(result.remaining_seconds / 60);
      html += `<div class="cooldown-banner"><svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/></svg><div><b>Cooldown active — ${mins} min remaining</b><p>Minimum ${mins} minutes between entry and exit.</p></div></div>`;
    }
    box.innerHTML = html;
  }

  /* ---- Visitors ---- */
  async function loadVisitors() {
    try {
      const q = new URLSearchParams({ page: String(visitorPage), page_size: String(listPageSize) });
      const n = $("#visitor-search")?.value.trim(), s = $("#visitor-status")?.value;
      if (n) q.set("name", n);
      if (s) q.set("status", s);
      const data = await api(`/api/visitors?${q}`);
      const counts = $("#visitor-counts");
      if (counts) {
        counts.replaceChildren(
          makeStatCard("Total Visitors", data.total),
          makeStatCard("Active Today", data.active, "green"),
          makeStatCard("Expired / Inactive", data.inactive),
        );
      }
      renderPagination("#visitor-page", visitorPage, data.total, listPageSize, (p) => { visitorPage = p; loadVisitors(); });
      if (!data.items.length) {
        setRows("#visitor-rows", []);
        const empty = document.createElement("tr");
        const td = document.createElement("td"); td.colSpan = 13;
        td.className = "empty-state"; td.style.padding = "40px";
        td.textContent = "No visitors found.";
        empty.append(td);
        $("#visitor-rows")?.append(empty);
        return;
      }
      setRows("#visitor-rows", data.items.map(v => {
        const tr = document.createElement("tr");
        const photoTd = document.createElement("td");
        if (v.photo_url) {
          const img = document.createElement("img");
          img.className = "cell-thumb"; img.src = v.photo_url; img.alt = v.name; img.loading = "lazy";
          photoTd.append(img);
        } else {
          photoTd.textContent = "—";
        }
        tr.append(photoTd);
        cell(tr, v.visitor_id, "cell-mono"); cell(tr, v.visitor_no, "cell-mono");
        cell(tr, v.name, "cell-strong"); cell(tr, v.company_name); cell(tr, v.location);
        cell(tr, v.host); cell(tr, v.purpose); cell(tr, v.contact_no);
        cell(tr, v.aadhaar_masked, "cell-mono"); cell(tr, fmt(v.expiration_timestamp));
        const statusTd = document.createElement("td");
        statusTd.append(makeBadge(v.status, v.status.toLowerCase()));
        tr.append(statusTd);
        const actions = document.createElement("td");
        actions.className = "cell-actions";
        actions.append(mkLink("Pass", `/api/visitors/${encodeURIComponent(v.visitor_id)}/id-card`));
        tr.append(actions);
        return tr;
      }));
    } catch (e) { notice(e.message, true); }
  }

  /* Visitor registration */
  $("#visitor-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const submit = $('button[type="submit"]', form);
    btnLoad(submit, true);
    try {
      const fd = uppercaseFormData(new FormData(form));
      const v = await api("/api/visitors", { method: "POST", body: fd });
      form.reset();
      const preview = $("#vf-photo-preview"); if (preview) preview.style.display = "none";
      $("#visitor-register-panel")?.setAttribute("hidden", "");
      notice(`Visitor pass issued: ${v.visitor_no}. Valid through today.`);
      showPreview("visitor", v);
      await loadVisitors();
    } catch (e) { notice(e.message, true); }
    finally { btnLoad(submit, false); }
  });

  /* ---- Canteen ---- */
  async function loadCanteenRecent() {
    try {
      const data = await api("/api/canteen/transactions?page=1&page_size=10");
      renderCanteenFeed("#canteen-recent", data.items);
    } catch (e) { notice(e.message, true); }
  }

  async function loadCanteenHistory() {
    try {
      const q = new URLSearchParams({ page: "1", page_size: "100" });
      const dateVal = $("#canteen-date")?.value;
      const resultVal = $("#canteen-result-filter")?.value;
      if (dateVal) q.set("business_date", dateVal);
      if (resultVal) q.set("result", resultVal);
      const data = await api(`/api/canteen/transactions?${q}`);
      renderCanteenTableRows("#canteen-history-rows", data.items);
      const day = await api(`/api/canteen/report${dateVal ? `?report_date=${encodeURIComponent(dateVal)}` : ""}`);
      const counts = $("#canteen-counts");
      if (counts) {
        counts.replaceChildren(
          makeStatCard("Successful Meals", day.successful_scans, "green"),
          makeStatCard("Rejected Scans", day.rejected_scans, "red"),
          makeStatCard("Unique People", day.unique_people, "blue"),
        );
      }
    } catch (e) { notice(e.message, true); }
  }

  function renderCanteenFeed(target, rows) {
    const container = $(target);
    if (!container) return;
    container.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "feed-empty"; empty.textContent = "No canteen scans yet today.";
      container.append(empty); return;
    }
    rows.forEach(t => {
      const item = document.createElement("div"); item.className = "feed-item";
      const left = document.createElement("div"); left.className = "feed-item-left";
      const info = document.createElement("div");
      const b = document.createElement("b"); b.textContent = t.person_id;
      const small = document.createElement("small"); small.textContent = fmtTime(t.scan_timestamp);
      info.append(b, small); left.append(info);
      const badge = makeBadge(
        t.scan_result, t.scan_result === "ACCEPTED" ? "meal" : "rejected"
      );
      item.append(left, badge);
      container.append(item);
    });
  }

  function renderCanteenTableRows(target, rows) {
    setRows(target, rows.map(t => {
      const tr = document.createElement("tr");
      // Photo column
      const photoTd = document.createElement("td");
      if (t.photo_url) {
        const img = document.createElement("img");
        img.className = "cell-thumb"; img.src = t.photo_url; img.alt = t.name || ""; img.loading = "lazy";
        photoTd.append(img);
      } else { photoTd.textContent = "—"; }
      tr.append(photoTd);
      // Name column
      cell(tr, t.name || "—", "cell-strong");
      cell(tr, fmt(t.scan_timestamp));
      cell(tr, t.person_id, "cell-mono");
      const typeTd = document.createElement("td");
      typeTd.append(makeBadge(t.person_type, t.person_type?.toLowerCase() || "unknown"));
      tr.append(typeTd);
      cell(tr, t.gate_entry_id ?? "—");
      const resultTd = document.createElement("td");
      resultTd.append(makeBadge(t.scan_result, t.scan_result?.toLowerCase()));
      tr.append(resultTd);
      cell(tr, t.rejection_reason || "—");
      return tr;
    }));
  }

  /* Canteen scan handler */
  $("#canteen-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      const result = await api("/api/canteen/scan", {
        method: "POST",
        body: JSON.stringify({ barcode: new FormData(form).get("barcode") }),
      });
      renderCanteenResult(result);
      beep(result.accepted);
      form.reset();
      await loadCanteenRecent();
    } catch (e) { notice(e.message, true); }
  });

  function renderCanteenResult(result) {
    const box = $("#canteen-result");
    if (!box) return;
    box.style.display = "block";
    box.className = `result-card ${result.accepted ? "result-accepted" : "result-rejected"}`;
    let html = `<div class="result-badge">`;
    if (result.accepted) {
      html += `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
      html += `<div><h2>Meal Accepted</h2><span>${result.reason}</span></div>`;
    } else {
      html += `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
      html += `<div><h2>Scan Rejected</h2><span>${result.reason}</span></div>`;
    }
    html += `</div>`;
    if (result.person) {
      const p = result.person;
      const photoHtml = p.photo_url
        ? `<img class="person-photo" src="${p.photo_url}" alt="${p.name}" loading="lazy">`
        : `<div class="person-photo-placeholder"><svg viewBox="0 0 20 20" fill="currentColor" width="24" height="24"><path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"/></svg></div>`;
      html += `<div class="result-person">${photoHtml}<div class="person-info">
        <div class="person-badges"><span class="badge badge-${p.person_type?.toLowerCase()}">${p.person_type}</span></div>
        <h3>${p.name}</h3><div class="person-meta"><span>ID: <b>${p.person_id}</b></span>${p.detail ? `<span>${p.detail}</span>` : ""}</div>
      </div></div>`;
    }
    if (result.gate_entry_time) {
      html += `<div style="margin-top:10px;font-size:11px;color:var(--text-3)">Gate entry: ${fmt(result.gate_entry_time)}</div>`;
    }
    box.innerHTML = html;
  }

  /* ---- Initial page ---- */
  let initial = "dashboard";
  try { initial = sessionStorage.getItem("wf-page") || initial; } catch {}
  if (!$(`#page-${initial}`) || !$(`.navitem[data-page="${initial}"]`))
    initial = $$(".navitem")[0]?.dataset.page || "dashboard";
  openPage(initial);

})();
