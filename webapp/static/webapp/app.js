(() => {
  const one = (s, root = document) => root.querySelector(s);
  const many = (s, root = document) => [...root.querySelectorAll(s)];
  const csrf = () => one('meta[name="csrf-token"]')?.content || one('input[name="csrfmiddlewaretoken"]')?.value || "";
  const api = async (url, options = {}) => {
    const headers = new Headers(options.headers || {});
    headers.set("X-CSRFToken", csrf());
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(url, {...options, headers, credentials: "same-origin"});
    if (!response.ok) {
      let message = `Request failed (${response.status})`;
      try { const data = await response.json(); message = data.detail || data.message || message; } catch {}
      throw new Error(message);
    }
    return response.status === 204 ? null : response.json().catch(() => null);
  };
  const notice = (message, error = false) => {
    const box = one("#notice"); if (!box) return;
    box.textContent = message; box.hidden = false; box.classList.toggle("error", error);
    clearTimeout(notice.timer); notice.timer = setTimeout(() => { box.hidden = true; }, 5000);
  };
  const cell = (row, value, className = "") => {
    const td = document.createElement("td"); td.textContent = value ?? "—"; if (className) td.className = className; row.append(td); return td;
  };
  const button = (label, className, action) => {
    const b = document.createElement("button"); b.type = "button"; b.className = className; b.textContent = label; b.addEventListener("click", action); return b;
  };
  const fmt = value => value ? new Date(value).toLocaleString() : "—";
  const link = (label, href) => { const a = document.createElement("a"); a.textContent = label; a.href = href; a.className = "secondary action-link"; a.target = "_blank"; a.rel = "noopener"; return a; };
  const setRows = (selector, rows) => { const target = one(selector); if (target) { target.replaceChildren(); rows.forEach(r => target.append(r)); } };
  const beep = accepted => { try { const C = window.AudioContext || window.webkitAudioContext; if (!C) return; const c = new C(), o=c.createOscillator(), g=c.createGain(); o.connect(g); g.connect(c.destination); o.type=accepted?"sine":"sawtooth"; o.frequency.value=accepted?660:190; g.gain.value=.12; o.start(); o.stop(c.currentTime+.2); o.onended=()=>c.close(); } catch {} };

  const login = one("#login-form");
  if (login) {
    login.addEventListener("submit", async event => {
      event.preventDefault(); one("#login-error").textContent = "";
      const data = Object.fromEntries(new FormData(login));
      try { await api("/api/auth/login", {method: "POST", body: JSON.stringify(data)}); location.reload(); }
      catch (error) { one("#login-error").textContent = error.message; }
    });
    return;
  }

  const pages = many(".page");
  let workerPage = 1, visitorPage = 1;
  const listPageSize = 25;
  const load = {
    dashboard: loadDashboard, workers: loadWorkers, visitors: loadVisitors,
    "gate-history": loadGateHistory, "canteen-history": loadCanteenHistory,
    gate: loadGateRecent, canteen: loadCanteenRecent,
  };
  function openPage(name) {
    pages.forEach(p => { p.hidden = p.id !== `page-${name}`; });
    many(".navitem").forEach(b => b.classList.toggle("active", b.dataset.page === name));
    try { sessionStorage.setItem("wf-page", name); } catch {}
    load[name]?.();
    if (name === "gate") setTimeout(() => one('#gate-form input[name="barcode"]')?.focus(), 20);
    if (name === "canteen") setTimeout(() => one('#canteen-form input[name="barcode"]')?.focus(), 20);
  }
  many("[data-page]").forEach(b => b.addEventListener("click", () => openPage(b.dataset.page)));
  many("[data-refresh]").forEach(b => b.addEventListener("click", () => load[b.dataset.refresh]?.()));
  one("#logout")?.addEventListener("click", async () => { try { await api("/api/auth/logout", {method: "POST"}); } finally { location.href = "/"; } });
  one("#worker-search")?.addEventListener("input", debounce(() => { workerPage=1; loadWorkers(); }, 250));
  one("#visitor-search")?.addEventListener("input", debounce(() => { visitorPage=1; loadVisitors(); }, 250));
  one("#visitor-status")?.addEventListener("change", () => { visitorPage=1; loadVisitors(); });
  one("#gate-date")?.addEventListener("change", loadGateHistory);
  one("#gate-result")?.addEventListener("change", loadGateHistory);
  one("#canteen-date")?.addEventListener("change", loadCanteenHistory);

  function debounce(fn, ms) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); }; }
  function renderPagination(target, page, total, size, change) {
    const box=one(target); if(!box) return;
    box.replaceChildren();
    const label=document.createElement("span"), first=total ? (page-1)*size+1 : 0, last=Math.min(page*size,total);
    label.textContent=`Showing ${first}–${last} of ${total}`; box.append(label);
    const controls=document.createElement("div");
    const previous=button("Previous","secondary compact",()=>change(page-1)); previous.disabled=page<=1;
    const current=document.createElement("span"); current.textContent=`Page ${page}`;
    const next=button("Next","secondary compact",()=>change(page+1)); next.disabled=page*size>=total;
    controls.append(previous,current,next); box.append(controls);
  }
  for (const formId of ["gate-form", "canteen-form"]) {
    const form = one(`#${formId}`), input = one('input[name="barcode"]', form);
    if (!input) continue;
    let times = [], timer, lastCode = "", lastAt = 0;
    input.addEventListener("keydown", event => {
      const now = Date.now();
      if (event.key === "Enter") { times=[]; return; }
      if (event.key.length !== 1) return;
      times = times.filter(t => now - t < 1000); times.push(now); clearTimeout(timer);
      timer = setTimeout(() => {
        const value = input.value.trim(), span = times.length > 1 ? times.at(-1) - times[0] : Infinity;
        if (value.length >= 4 && times.length >= 4 && span < 500 && !(lastCode === value && Date.now()-lastAt < 1000)) {
          lastCode=value; lastAt=Date.now(); times=[]; form.requestSubmit();
        }
      }, 140);
    });
  }

  // Camera capture uses browser APIs and produces the same bounded JPG uploads
  // accepted by the existing photo-validation service.
  let cameraStream = null, cameraForm = null;
  const cameraDialog = one("#camera-dialog"), video = one("#camera-dialog video");
  const stopCamera = () => { cameraStream?.getTracks().forEach(t => t.stop()); cameraStream=null; if(video) video.srcObject=null; };
  many("[data-camera]").forEach(b => b.addEventListener("click", async () => {
    cameraForm=one(`#${b.dataset.camera}`);
    try { cameraStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:"user"}},audio:false}); video.srcObject=cameraStream; cameraDialog.showModal(); }
    catch(e) { stopCamera(); notice(`Camera unavailable: ${e.message || "permission denied"}`,true); }
  }));
  cameraDialog?.addEventListener("close", stopCamera);
  one("#capture-photo")?.addEventListener("click", async () => {
    if (!video?.videoWidth || !cameraForm) { notice("The camera is still starting. Try again in a moment.",true); return; }
    const canvas=document.createElement("canvas"), ratio=8/9, source=video.videoWidth/video.videoHeight;
    let sx=0, sy=0, sw=video.videoWidth, sh=video.videoHeight;
    if(source>ratio){sw=video.videoHeight*ratio;sx=(video.videoWidth-sw)/2;}else{sh=video.videoWidth/ratio;sy=(video.videoHeight-sh)/2;}
    try {
      let blob=null;
      for(const size of [720,540,360,240,160,120,80,48]){
        canvas.width=Math.round(size*ratio);canvas.height=size;canvas.getContext("2d").drawImage(video,sx,sy,sw,sh,0,0,canvas.width,canvas.height);
        for(const quality of [.88,.76,.64,.52,.4,.3]){blob=await new Promise(resolve=>canvas.toBlob(resolve,"image/jpeg",quality));if(blob&&blob.size<=200*1024)break;}
        if(blob&&blob.size<=200*1024)break;
      }
      if(!blob||blob.size>200*1024)throw new Error("Captured photo exceeds 200 KB.");
      const file=new File([blob],`workforce-photo-${Date.now()}.jpg`,{type:"image/jpeg"}), input=one('input[name="photo"]',cameraForm), transfer=new DataTransfer();
      transfer.items.add(file);input.files=transfer.files;cameraDialog.close();notice("Photo captured and ready to submit.");
    } catch(e){notice(e.message,true);}
  });
  async function loadDashboard() {
    try {
      const [summary, gate, meals] = await Promise.all([api("/api/summary"), api("/api/gate/report"), api("/api/canteen/report")]);
      for (const [id, value] of [["dash-total", summary.total], ["dash-active", summary.active], ["dash-inactive", summary.inactive]]) one(`#${id}`).textContent = value;
      const cards = [["Gate entries", gate.accepted_entries], ["Gate exits", gate.accepted_exits], ["Meal scans", meals.successful_scans]];
      one("#daily-summary").replaceChildren(...cards.map(([label, value]) => { const d = document.createElement("div"); const s = document.createElement("span"); const b = document.createElement("b"); s.textContent = label; b.textContent = value; d.append(s,b); return d; }));
    } catch (e) { notice(e.message, true); }
  }
  async function loadWorkers() {
    try {
      const q = new URLSearchParams({page: String(workerPage), page_size: String(listPageSize)}); const term = one("#worker-search")?.value.trim(); if (term) q.set("name", term);
      const data = await api(`/api/workers?${q}`);
      one("#worker-total").textContent = data.total; one("#worker-active").textContent = data.active; one("#worker-inactive").textContent = data.inactive;
      renderPagination("#worker-page",workerPage,data.total,listPageSize,next=>{workerPage=next;loadWorkers();});
      setRows("#worker-rows", data.items.map(w => {
        const tr = document.createElement("tr"); const photo = document.createElement("td"); const img = document.createElement("img"); img.className = "thumb"; img.src = w.photo_url; img.alt = `${w.name} photo`; photo.append(img); tr.append(photo);
        cell(tr,w.worker_id,"mono"); cell(tr,w.worker_no,"mono"); cell(tr,w.name,"strong"); cell(tr,w.contractor_name); cell(tr,w.joining_date); cell(tr,w.contact_no); cell(tr,w.emergency_contact); cell(tr,w.aadhaar_masked,"mono");
        const status = cell(tr,w.status); status.className = `status-cell ${w.status.toLowerCase()}`;
        const actions = document.createElement("td"); actions.append(link("ID card PDF", `/api/workers/${encodeURIComponent(w.worker_id)}/id-card`));
        actions.append(button(w.status === "Active" ? "Deactivate" : "Activate", "secondary compact", async () => { try { await api(`/api/workers/${encodeURIComponent(w.worker_id)}/status`, {method:"POST", body:JSON.stringify({status:w.status === "Active" ? "Inactive" : "Active"})}); loadWorkers(); } catch(e) { notice(e.message,true); } })); tr.append(actions); return tr;
      }));
    } catch (e) { notice(e.message, true); }
  }

  one("#worker-form")?.addEventListener("submit", async event => {
    event.preventDefault(); const form = event.currentTarget; const submit = one("button[type=submit]", form); submit.disabled = true;
    try { const result = await api("/api/workers", {method:"POST", body:new FormData(form)}); form.reset(); notice(`Worker registered. Worker ID: ${result.worker_id}; number: ${result.worker_no}.`); openPage("workers"); }
    catch(e) { notice(e.message,true); } finally { submit.disabled = false; }
  });

  async function loadGateRecent() {
    try { const data = await api("/api/gate/transactions?page=1&page_size=10"); renderGateRows("#gate-recent",data.items); }
    catch(e) { notice(e.message,true); }
  }
  async function loadGateHistory() {
    try { const q = new URLSearchParams({page:"1",page_size:"100"}); const d=one("#gate-date")?.value, r=one("#gate-result")?.value; if(d) q.set("event_date",d); if(r) q.set("result",r); const data=await api(`/api/gate/transactions?${q}`); renderGateRows("#gate-history-rows",data.items,true); }
    catch(e) { notice(e.message,true); }
  }
  function renderGateRows(target, rows, barcode = false) {
    setRows(target, rows.map(t => { const tr=document.createElement("tr"); cell(tr,fmt(t.scan_timestamp)); cell(tr,t.person_id,"mono"); cell(tr,t.person_type); cell(tr,t.event_type); if(barcode) cell(tr,t.barcode_scanned,"mono"); cell(tr,t.validation_result); cell(tr,t.rejection_reason || "—"); return tr; }));
  }
  one("#gate-form")?.addEventListener("submit", async event => {
    event.preventDefault(); const form=event.currentTarget; const barcode=new FormData(form).get("barcode");
    try { const result=await api("/api/gate/scan",{method:"POST",body:JSON.stringify({barcode})}); const box=one("#gate-result"); box.textContent=`${result.accepted ? "ACCEPTED" : "REJECTED"} · ${result.event_type || "Gate scan"} · ${result.reason}${result.person ? ` · ${result.person.name} (${result.person.person_id})` : ""}${result.remaining_seconds ? ` · Try again in ${Math.ceil(result.remaining_seconds/60)} min` : ""}`; box.classList.toggle("rejected",!result.accepted); beep(result.accepted); form.reset(); await loadGateRecent(); }
    catch(e) { notice(e.message,true); }
  });

  async function loadVisitors() {
    try { const q=new URLSearchParams({page:String(visitorPage),page_size:String(listPageSize)}); const n=one("#visitor-search")?.value.trim(), s=one("#visitor-status")?.value; if(n) q.set("name",n); if(s) q.set("status",s); const data=await api(`/api/visitors?${q}`);
      one("#visitor-counts").replaceChildren(...[["Total visitors",data.total],["Active today",data.active],["Expired / inactive",data.inactive]].map(([label,value])=>{const d=document.createElement("div"),s=document.createElement("span"),b=document.createElement("b");s.textContent=label;b.textContent=value;d.append(s,b);return d;}));
      setRows("#visitor-rows",data.items.map(v=>{const tr=document.createElement("tr"),photo=document.createElement("td");if(v.photo_url){const img=document.createElement("img");img.className="thumb";img.src=v.photo_url;img.alt=`${v.name} photo`;photo.append(img);}else photo.textContent="—";tr.append(photo);cell(tr,v.visitor_id,"mono");cell(tr,v.visitor_no,"mono");cell(tr,v.name,"strong");cell(tr,v.company_name);cell(tr,v.location);cell(tr,v.host);cell(tr,v.purpose);cell(tr,v.contact_no);cell(tr,v.aadhaar_masked,"mono");cell(tr,fmt(v.expiration_timestamp));cell(tr,v.status);const actions=document.createElement("td");actions.append(link("Pass PDF",`/api/visitors/${encodeURIComponent(v.visitor_id)}/id-card`));tr.append(actions);return tr;}));
      renderPagination("#visitor-page",visitorPage,data.total,listPageSize,next=>{visitorPage=next;loadVisitors();});
    } catch(e) { notice(e.message,true); }
  }
  one("#visitor-form")?.addEventListener("submit", async event=>{event.preventDefault();const form=event.currentTarget;try{const v=await api("/api/visitors",{method:"POST",body:new FormData(form)});form.reset();notice(`Visitor pass issued: ${v.visitor_no}. Valid through today.`);await loadVisitors();}catch(e){notice(e.message,true);}});

  async function loadCanteenRecent() { try {const data=await api("/api/canteen/transactions?page=1&page_size=10");renderMealRows("#canteen-recent",data.items,false);}catch(e){notice(e.message,true);} }
  async function loadCanteenHistory() { try {const q=new URLSearchParams({page:"1",page_size:"100"});const dateValue=one("#canteen-date")?.value;if(dateValue)q.set("business_date",dateValue);const data=await api(`/api/canteen/transactions?${q}`);renderMealRows("#canteen-history-rows",data.items,true);const day=await api(`/api/canteen/report${dateValue?`?report_date=${encodeURIComponent(dateValue)}`:""}`);one("#canteen-counts").replaceChildren(...[["Successful meals",day.successful_scans],["Rejected scans",day.rejected_scans],["Unique people",day.unique_people]].map(([label,value])=>{const d=document.createElement("div"),s=document.createElement("span"),b=document.createElement("b");s.textContent=label;b.textContent=value;d.append(s,b);return d;}));}catch(e){notice(e.message,true);} }
  function renderMealRows(target,rows,history){setRows(target,rows.map(t=>{const tr=document.createElement("tr");cell(tr,fmt(t.scan_timestamp));cell(tr,t.person_id,"mono");cell(tr,t.person_type);if(history)cell(tr,t.gate_entry_id ?? "—");cell(tr,t.scan_result);cell(tr,t.rejection_reason||"—");return tr;}));}
  one("#canteen-form")?.addEventListener("submit",async event=>{event.preventDefault();const form=event.currentTarget;try{const result=await api("/api/canteen/scan",{method:"POST",body:JSON.stringify({barcode:new FormData(form).get("barcode")})});const box=one("#canteen-result");box.textContent=`${result.accepted?"ACCEPTED":"REJECTED"} · ${result.reason}${result.person?` · ${result.person.name} (${result.person.person_id})`:""}`;box.classList.toggle("rejected",!result.accepted);beep(result.accepted);form.reset();await loadCanteenRecent();}catch(e){notice(e.message,true);}});

  let initial = "dashboard"; try { initial=sessionStorage.getItem("wf-page") || initial; } catch {}
  if (!one(`#page-${initial}`) || !one(`.navitem[data-page="${initial}"]`)) initial = many(".navitem")[0]?.dataset.page || "dashboard";
  openPage(initial);
})();
