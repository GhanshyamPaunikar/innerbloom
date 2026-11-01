
// =========================================================================
// CONFIG + UTILITIES
// =========================================================================
// Backend base URL. Matches the uvicorn default in the README (port 5000).
// Override at runtime via `window.INNERBLOOM_API` before this script loads.
const API = (window.INNERBLOOM_API || window.REFLECT_API || document.querySelector('meta[name="innerbloom-api"]')?.content || (["/app", "/index.html"].includes(location.pathname) ? location.origin : "http://127.0.0.1:5000")).replace(/\/$/, "");
const DRAFT_KEY = "innerbloom.draft";
const SPOTIFY_VERIFIER_KEY = "innerbloom.spotify.verifier";
const SPOTIFY_REDIRECT_KEY = "innerbloom.spotify.redirect";

const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

function toast(msg, type = "success", ms = 2400) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  $("toast-host").appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function fmtDate(iso) {
  try {
    const d = new Date(iso);
    const now = new Date();
    const day = 86400000;
    const diff = now - d;
    if (diff < day && d.getDate() === now.getDate())
      return "Today, " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diff < 2 * day) return "Yesterday, " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diff < 7 * day) return d.toLocaleDateString([], { weekday: "long" }) + ", " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
  } catch { return iso; }
}
function fmtDateShort(iso) {
  try { return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" }); }
  catch { return iso; }
}
function fmtMonthYear(iso) {
  try { return new Date(iso).toLocaleDateString([], { month: "long", year: "numeric" }); }
  catch { return iso; }
}
function emotionColor(e) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--e-${(e || "neutral").toLowerCase()}`).trim() || "#a1a1aa";
}
function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function greeting() {
  const h = new Date().getHours();
  if (h < 5) return "Late night thoughts.";
  if (h < 12) return "Good morning. What's opening up today?";
  if (h < 17) return "Afternoon check-in.";
  if (h < 21) return "Evening — time to unwind on the page.";
  return "Winding down.";
}
function mdToHtml(s) { return escapeHtml(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>"); }

async function api(path, opts = {}) {
  const r = await fetch(API + path, { ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    throw new Error(`${r.status}: ${txt.slice(0, 120)}`);
  }
  return r.json();
}

// =========================================================================
// NAVIGATION
// =========================================================================
const TITLES = {
  write: () => ["A little room to think.", "Start wherever you are."],
  entries: () => ["A life, in little moments.", "Everything you’ve made space for."],
  chat: () => ["A conversation with yourself.", "Follow a thought. Find a connection."],
  insights: () => ["See what’s taking shape.", "Connections across your recent pages."],
  graph: () => ["The shape of your memories.", "Connections emerge as you write."],
  people: () => ["The people in your pages.", "Return to the moments you share."],
  music: () => ["The soundtrack to your days.", "A closer look at what you listen to and how you feel."],
  settings: () => ["Make yourself at home.", "Your space. Your preferences. Your data."],
};

const VIEW_KEY = "innerbloom.activeView";
function switchView(view) {
  if (!TITLES[view]) return;
  document.body.classList.remove("focus-writing");
  document.dispatchEvent(new CustomEvent("innerbloom:view", { detail: view }));
  $$(".view").forEach(v => v.classList.remove("active"));
  $$(".nav-item").forEach(n => n.classList.remove("active"));
  const viewEl = $(`view-${view}`);
  if (!viewEl) return;
  viewEl.classList.add("active");
  const nav = document.querySelector(`.nav-item[data-view="${view}"]`);
  document.querySelectorAll(".nav-item[data-view]").forEach(el => el.removeAttribute("aria-current"));
  if (nav) { nav.classList.add("active"); nav.setAttribute("aria-current", "page"); }
  const [t, g] = TITLES[view]();
  $("page-title").textContent = t;
  $("greeting").textContent = g;
  $("sidebar").classList.remove("open");
  $("menu-btn").setAttribute("aria-expanded", "false");
  document.querySelector(".main").scrollTop = 0;

  // Persist so page reloads (e.g. Live Server) don't snap back to default
  try { localStorage.setItem(VIEW_KEY, view); } catch {}

  if (view === "entries") loadEntries();
  if (view === "chat") loadChatHistory();
  if (view === "insights") {
    loadInsights(); loadContradictions(); loadTriggers(); loadWellbeing(); loadNarrative();
  }
  if (view === "graph") { loadGraph(); }
  else { stopGraphSim(); }
  if (view === "people") loadPeople();
  if (view === "music") loadMusic();
  if (view === "people") loadPeople();
  if (view === "settings") renderSettings();
}

$$(".nav-item").forEach(n => {
  const v = n.getAttribute("data-view");
  if (v) n.addEventListener("click", () => switchView(v));
});
$("menu-btn")?.addEventListener("click", () => { const open = $("sidebar").classList.toggle("open"); $("menu-btn").setAttribute("aria-expanded", String(open)); });
$("streak-card").addEventListener("click", () => switchView("insights"));

// =========================================================================
// HEALTH + STREAK
// =========================================================================
async function updateHealth() {
  if(document.querySelector('meta[name="innerbloom-demo"]')) { $("health-badge").textContent="Sample workspace"; $("health-badge").className="badge"; return; }
  try {
    const r = await api("/health");
    if (r.ollama === "up") {
      // Pull the model name from the root endpoint when we know it; this
      // keeps the badge honest after a user switches INNERBLOOM_MODEL.
      let modelName = "Ollama";
      try {
        const root = await api("/");
        if (r.provider === "gemini") modelName = "Gemini";
        else if (root.model) modelName = String(root.model).split(":")[0];
      } catch {}
      $("health-badge").innerHTML = `<span style="color:var(--success)">●</span> ${escapeHtml(modelName)} ready`;
      $("health-badge").className = "badge green";
    } else {
      $("health-badge").innerHTML = '<span style="color:var(--danger)">●</span> ollama offline';
      $("health-badge").className = "badge red";
    }
  } catch {
    $("health-badge").innerHTML = '<span style="color:var(--danger)">●</span> backend offline';
    $("health-badge").className = "badge red";
  }
}

async function updateStreak() {
  try {
    const s = await api("/stats");
    $("streak-num").innerHTML = `${s.streak_current}<span class="unit">day${s.streak_current === 1 ? "" : "s"}</span>`;
    $("streak-sub").textContent = `Longest: ${s.streak_longest} · ${s.total_entries} total`;
    document.dispatchEvent(new CustomEvent("innerbloom:stats", { detail: s }));
  } catch {}
}

// =========================================================================
// WRITE VIEW
// =========================================================================
const entryText = $("entry-text");
const entryTitle = $("entry-title");

try {
  entryText.value = localStorage.getItem(DRAFT_KEY) || "";
  entryTitle.value = localStorage.getItem(DRAFT_KEY + ".title") || "";
  $("entry-intensity").value = localStorage.getItem(DRAFT_KEY + ".intensity") || "";
} catch {}

function updateWordCount() {
  const n = entryText.value.trim() ? entryText.value.trim().split(/\s+/).length : 0;
  $("word-count").textContent = `${n} word${n === 1 ? "" : "s"}`;
}
updateWordCount();

// =========================================================================
// CRISIS DETECTION
// =========================================================================
const CRISIS_KEYWORDS = [
  "want to die", "kill myself", "end my life", "suicidal", "suicide",
  "no reason to live", "can't go on", "cannot go on", "give up on life",
  "not worth living", "better off dead", "end it all", "want to disappear",
  "don't want to exist", "no point in living", "life is not worth",
  "hate being alive", "wish i was dead", "want to be dead", "tired of living",
  "don't want to live", "ready to die", "planning to kill", "hurt myself",
  "self harm", "cutting myself", "no will to live",
];

let crisisShown = false;

function checkCrisisKeywords(text) {
  if (crisisShown) return;
  const lower = text.toLowerCase();
  if (CRISIS_KEYWORDS.some(k => lower.includes(k))) {
    crisisShown = true;
    $("crisis-modal").classList.add("active");
  }
}

$("crisis-close").addEventListener("click", () => {
  $("crisis-modal").classList.remove("active");
});

let draftTimer;
function persistDraft() {
  try {
    localStorage.setItem(DRAFT_KEY, entryText.value);
    localStorage.setItem(DRAFT_KEY + ".title", entryTitle.value);
    localStorage.setItem(DRAFT_KEY + ".intensity", $("entry-intensity").value);
    $("draft-status").textContent = "Draft saved on this device";
  } catch { $("draft-status").textContent = "Draft storage unavailable — save your entry"; }
}
function clearSavedDraft() {
  clearTimeout(draftTimer);
  try { [DRAFT_KEY, DRAFT_KEY + ".title", DRAFT_KEY + ".intensity"].forEach(k => localStorage.removeItem(k)); } catch {}
  $("entry-intensity").value = "";
  $("draft-status").textContent = "A fresh page";
}
function draftChanged() {
  updateWordCount(); checkCrisisKeywords(entryText.value);
  $("draft-status").textContent = "Saving draft…";
  clearTimeout(draftTimer); draftTimer = setTimeout(persistDraft, 400);
}
entryText.addEventListener("input", draftChanged);
entryTitle.addEventListener("input", draftChanged);
$("entry-intensity").addEventListener("change", draftChanged);
window.addEventListener("pagehide", () => { if (entryText.value || entryTitle.value) persistDraft(); });
$("clear-btn").addEventListener("click", () => {
  if ((!entryText.value.trim() && !entryTitle.value.trim()) || confirm("Clear the current draft?")) {
    entryText.value = ""; entryTitle.value = ""; clearSavedDraft(); updateWordCount();
  }
});

async function saveEntry() {
  const text = entryText.value.trim();
  if (!text) { toast("Write something first.", "error"); return; }
  const btn = $("save-btn"); const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span>Saving & reflecting…</span>';
  try {
    const saved = await api("/save", {
      method: "POST",
      body: JSON.stringify({ text, title: entryTitle.value.trim() || null, mood: $("entry-intensity").value ? Number($("entry-intensity").value) : null }),
    });
    entryText.value = ""; entryTitle.value = "";
    crisisShown = false;
    clearSavedDraft(); updateWordCount();
    const hardEmotions = ["sad", "anxious", "angry", "overwhelmed", "lonely", "frustrated", "tired"];
    const emotion = saved?.entry?.emotion || "";
    if (hardEmotions.includes(emotion)) {
      const compassionMsgs = [
        "Entry saved. Be gentle with yourself — feeling this is part of being human.",
        "Saved. Whatever you're carrying right now, you don't have to carry it perfectly.",
        "Entry saved. It takes courage to put hard feelings into words. That matters.",
        "Saved. You showed up and wrote. That alone is something.",
        "Entry saved. Hard days pass. You're still here, and that counts.",
      ];
      toast(compassionMsgs[Math.floor(Math.random() * compassionMsgs.length)], "success", 4000);
    } else {
      toast("Entry saved · analyzed", "success");
    }
    updateStreak(); loadPrompt();
    document.dispatchEvent(new Event("innerbloom:saved"));
    try { localStorage.removeItem(ANNIV_CACHE_KEY); } catch {}
    loadAnniversary();
  } catch (e) {
    toast("Couldn't save. Is Ollama running?", "error");
  } finally {
    btn.disabled = false; btn.innerHTML = originalHtml;
  }
}
$("save-btn").addEventListener("click", saveEntry);

async function loadPrompt() {
  $("prompt-text").textContent = "…";
  try {
    const r = await api("/prompt");
    $("prompt-text").textContent = r.prompt && !r.prompt.startsWith('[LLM error') ? r.prompt : "What's one thing you noticed today that you'd usually overlook?";
  } catch {
    $("prompt-text").textContent = "What's one thing you noticed today that you'd usually overlook?";
  }
}
$("refresh-prompt").addEventListener("click", loadPrompt);

// --- Month-ago surfacing (pill trigger + click-to-open modal) -------------
// 1. On boot, ask /anniversary (without reflection — fast) just to find out
//    if there's anything from ~30 days ago. If so, reveal the small pill.
// 2. Clicking the pill opens the modal and lazily fetches the full version
//    (with reflection) the first time. Subsequent opens reuse the cached fetch.
const ANNIV_CACHE_KEY = "innerbloom.anniv.cache";
let _annivCached = null;          // {available, data, day, fullLoaded}

async function loadAnniversary() {
  const pill = $("anniv-pill");
  if (!pill) return;
  const today = new Date().toISOString().slice(0, 10);

  // Same-day cache reuse — avoid re-fetching on every navigation back to Write.
  try {
    const raw = localStorage.getItem(ANNIV_CACHE_KEY);
    if (raw) {
      const c = JSON.parse(raw);
      if (c.day === today) {
        _annivCached = c;
        if (c.available) showAnnivPill(c.data);
        return;
      }
    }
  } catch {}

  // Quick probe (no reflection) — tells us whether the pill should show.
  try {
    const r = await api("/anniversary?days=30&spread=6&with_reflection=false");
    const payload = { day: today, available: !!(r && r.available), data: r, fullLoaded: false };
    _annivCached = payload;
    try { localStorage.setItem(ANNIV_CACHE_KEY, JSON.stringify(payload)); } catch {}
    if (payload.available) showAnnivPill(r);
    else pill.style.display = "none";
  } catch {
    pill.style.display = "none";
  }
}

function showAnnivPill(r) {
  const pill = $("anniv-pill");
  if (!pill) return;
  const meta = $("anniv-pill-meta");
  const then = r.then || {};
  const emo = (then.top_emotion && then.top_emotion[0]) || "";
  if (meta) {
    meta.textContent = emo ? `you were feeling ${emo}` : "see what shifted";
  }
  pill.style.display = "inline-flex";
}

function openAnnivModal() {
  const back = $("anniv-modal-backdrop");
  const body = $("anniv-modal-body");
  if (!back || !body) return;
  back.classList.add("active");
  if (_annivCached && _annivCached.data) {
    renderAnnivModalBody(_annivCached.data);
    if (!_annivCached.fullLoaded && _annivCached.data.reflection == null) {
      // Lazy-load the LLM reflection.
      body.insertAdjacentHTML("afterbegin",
        `<div class="anniv-reflect-loading" id="anniv-reflect-loading">
           <div class="spinner"></div> Drafting a then-vs-now reflection…
         </div>`);
      (async () => {
        try {
          const full = await api("/anniversary?days=30&spread=6&with_reflection=true");
          if (full && full.available) {
            _annivCached.data = full;
            _annivCached.fullLoaded = true;
            try { localStorage.setItem(ANNIV_CACHE_KEY, JSON.stringify(_annivCached)); } catch {}
            renderAnnivModalBody(full);
          }
        } catch {
          const loading = $("anniv-reflect-loading");
          if (loading) loading.remove();
        }
      })();
    }
  } else {
    body.innerHTML = `<div class="anniv-reflect-loading">Nothing from a month ago — keep writing and it'll fill in.</div>`;
  }
}

function closeAnnivModal() {
  $("anniv-modal-backdrop")?.classList.remove("active");
}

function renderAnnivModalBody(r) {
  const body = $("anniv-modal-body");
  if (!body) return;
  const then = r.then || {};
  const now  = r.now  || {};
  const fmtDate = iso => {
    try { return new Date(iso).toLocaleDateString([], { month: "long", day: "numeric" }); }
    catch { return iso || ""; }
  };
  const renderCol = (label, w) => {
    if (!w || !w.count) {
      return `
        <div class="anniv-col">
          <div class="anniv-col-label">${escapeHtml(label)}</div>
          <div style="color:var(--text-dim);font-size:12.5px;">No entries in this window.</div>
        </div>`;
    }
    const emo = w.top_emotion ? w.top_emotion[0] : "neutral";
    const emoColor = `var(--e-${emo})`;
    const tagsHtml = (w.tags || []).slice(0, 4).map(([t, c]) =>
      `<span class="anniv-tag">#${escapeHtml(t)} ${c > 1 ? `<span style="color:var(--text-dim);">·${c}</span>` : ""}</span>`).join("");
    return `
      <div class="anniv-col">
        <div class="anniv-col-label">${escapeHtml(label)} · ${escapeHtml(fmtDate(w.date_center))}</div>
        <div class="anniv-col-emo">
          <span class="dot" style="background:${emoColor};"></span>
          ${escapeHtml(emo)}
          ${w.avg_intensity != null ? `<span style="color:var(--text-dim);font-size:12px;margin-left:4px;">${w.avg_intensity}/10</span>` : ""}
        </div>
        <div class="anniv-col-meta">${w.count} ${w.count === 1 ? "entry" : "entries"} in this window</div>
        ${tagsHtml ? `<div class="anniv-tags">${tagsHtml}</div>` : ""}
      </div>`;
  };

  const rf = r.reflection || {};
  const cleanCite = s => (s || "").replace(/\[([a-z0-9]{4,8})\]/g, (m, id) =>
    `<em title="entry ${id}">[${id}]</em>`);
  const reflectHtml = (rf.same || rf.shifted || rf.avoiding || rf.becoming) ? `
    <div class="anniv-reflect">
      ${rf.same     ? `<div class="anniv-reflect-key">Same</div>     <div class="anniv-reflect-val">${cleanCite(escapeHtml(rf.same))}</div>` : ""}
      ${rf.shifted  ? `<div class="anniv-reflect-key">Shifted</div>  <div class="anniv-reflect-val">${cleanCite(escapeHtml(rf.shifted))}</div>` : ""}
      ${rf.avoiding ? `<div class="anniv-reflect-key">Avoiding</div> <div class="anniv-reflect-val">${cleanCite(escapeHtml(rf.avoiding))}</div>` : ""}
      ${rf.becoming ? `<div class="anniv-reflect-key">Becoming</div> <div class="anniv-reflect-val">${cleanCite(escapeHtml(rf.becoming))}</div>` : ""}
    </div>` : "";

  const citeChips = (r.reflection_citations || []).slice(0, 5).map(c => `
    <span class="cite-pill" data-id="${c.id}" title="${escapeHtml(c.title || "")} · ${escapeHtml(c.date)}">
      <span class="dot" style="background:var(--e-${c.emotion});"></span>${escapeHtml(c.date)}
    </span>`).join("");

  body.innerHTML = `
    <div class="anniv-grid">
      ${renderCol("Then", then)}
      ${renderCol("Now",  now)}
    </div>
    ${reflectHtml}
    ${citeChips ? `<div class="anniv-actions">${citeChips}</div>` : ""}
  `;

  body.querySelectorAll(".cite-pill").forEach(el => {
    el.addEventListener("click", async () => {
      const id = el.getAttribute("data-id");
      try { const e = await api(`/journal/${id}`); closeAnnivModal(); openEntry(e); } catch {}
    });
  });
}

// Wire up pill + modal close + backdrop-click-to-dismiss + Escape key.
$("anniv-pill")?.addEventListener("click", openAnnivModal);
$("anniv-modal-close")?.addEventListener("click", closeAnnivModal);
$("anniv-modal-backdrop")?.addEventListener("click", (ev) => {
  if (ev.target === $("anniv-modal-backdrop")) closeAnnivModal();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && $("anniv-modal-backdrop")?.classList.contains("active")) {
    closeAnnivModal();
  }
});

// Person CRM drawer: dismiss on backdrop click + Escape.
$("person-modal")?.addEventListener("click", (ev) => {
  if (ev.target === $("person-modal")) closePersonModal();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && $("person-modal")?.classList.contains("active")) closePersonModal();
});

// Dictation never falls back to a browser's remote recognition service.
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null, listening = false;
const mic = $("mic-btn");
if (SpeechRecognition && "processLocally" in SpeechRecognition.prototype) {
  recognition = new SpeechRecognition();
  recognition.processLocally = true;
  recognition.continuous = true; recognition.interimResults = true; recognition.lang = "en-US";
  let baseText = "";
  recognition.onresult = ev => {
    let interim = "";
    for (let i=ev.resultIndex; i<ev.results.length; i++) {
      if (ev.results[i].isFinal) baseText += ev.results[i][0].transcript + " ";
      else interim += ev.results[i][0].transcript;
    }
    entryText.value = (baseText + interim).trim(); draftChanged();
  };
  recognition.onend = () => { listening = false; mic.classList.remove("listening"); mic.setAttribute("aria-pressed","false"); persistDraft(); };
  recognition.onerror = () => toast("On-device dictation is unavailable. Check your browser’s local language pack and microphone permission.", "error", 6000);
  mic.addEventListener("click", async () => {
    if (listening) { recognition.stop(); return; }
    try {
      if (SpeechRecognition.available) {
        const status = await SpeechRecognition.available({ langs:["en-US"], processLocally:true });
        if (status !== "available") { toast("Install an English on-device speech pack in your browser to use local dictation.", "error", 6000); return; }
      }
      baseText = entryText.value ? entryText.value.trimEnd() + " " : "";
      recognition.start(); listening=true; mic.classList.add("listening"); mic.setAttribute("aria-pressed","true");
    } catch { toast("Couldn’t start on-device dictation. Your audio has not been sent to a remote service.", "error", 5000); }
  });
} else {
  mic.setAttribute("aria-disabled", "true");
  mic.title = "This browser does not support on-device dictation";
  mic.addEventListener("click", () => toast("This browser doesn’t support on-device dictation. Remote speech recognition is disabled to keep your audio local.", "error", 6000));
}

// =========================================================================
// ENTRIES VIEW
// =========================================================================
let allEntries = [];
let currentEmotionFilter = null;
const EMOTION_FILTERS = ["happy", "sad", "anxious", "calm", "grateful", "frustrated", "excited", "reflective", "hopeful"];

function renderEmotionChips() {
  const host = $("emotion-chips");
  host.innerHTML = `<label for="mood-filter">Feeling</label><select id="mood-filter" aria-label="Filter entries by feeling"><option value="">All feelings</option>${EMOTION_FILTERS.map(e=>`<option value="${e}">${e.charAt(0).toUpperCase()+e.slice(1)}</option>`).join('')}</select><span class="filter-caption">A different way back to a moment.</span>`;
  $("mood-filter").value=currentEmotionFilter||'';
  $("mood-filter").onchange=ev=>{currentEmotionFilter=ev.target.value||null;renderEntries();};
}

async function loadEntries() {
  try {
    const r = await api("/journal");
    allEntries = r.entries || [];
    renderEmotionChips(); renderEntries();
    document.dispatchEvent(new CustomEvent("innerbloom:entries", { detail: allEntries }));
  } catch {
    $("entries-list").innerHTML = `<div class="empty"><h3>Backend unreachable</h3><p>Start the local app and try again.<code>python run_local.py</code></p></div>`;
  }
}

function renderEntries() {
  renderEmotionChips();
  const q = $("search-input").value.trim().toLowerCase();
  const host = $("entries-list"); host.innerHTML = "";

  let list = [...allEntries];
  if (currentEmotionFilter) list = list.filter(e => (e.emotion || "").toLowerCase() === currentEmotionFilter);
  if (q) list = list.filter(e =>
    (e.text || "").toLowerCase().includes(q) ||
    (e.title || "").toLowerCase().includes(q) ||
    (e.summary || "").toLowerCase().includes(q) ||
    (e.tags || []).some(t => t.toLowerCase().includes(q))
  );

  if (!list.length) {
    $("entries-count").textContent = "0 MOMENTS FOUND";
    host.innerHTML = `<div class="empty">
      <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>
      <h3>${allEntries.length ? "No matching moments." : "Your first page is waiting."}</h3>
      <p>${allEntries.length ? "Try another search or mood filter." : "Start with a thought. Innerbloom will help you find its threads."}</p>
    </div>`;
    return;
  }

  // Group by month
  if (window.innerbloomDateFilter) list = list.filter(e => (e.timestamp || "").slice(0,10) === window.innerbloomDateFilter);
  list.sort((a,b) => $("entry-sort").value === "oldest" ? new Date(a.timestamp)-new Date(b.timestamp) : new Date(b.timestamp)-new Date(a.timestamp));
  $("entries-count").textContent = `${list.length} ${list.length === 1 ? "MOMENT" : "MOMENTS"} KEPT`;
  if (!list.length) { host.innerHTML = '<div class="empty"><h3>No moments on this day.</h3><p>Choose another date, or clear the date filter.</p></div>'; return; }
  let lastMonth = "";
  list.forEach(e => {
    const m = fmtMonthYear(e.timestamp);
    if (m !== lastMonth) {
      const h = document.createElement("div");
      h.className = "month-group-label";
      h.textContent = m;
      host.appendChild(h);
      lastMonth = m;
    }
    const c = document.createElement("div");
    c.className = "entry-card";
    const tags = (e.tags || []).slice(0, 5).map(t => `<span class="tag">#${escapeHtml(t)}</span>`).join("");
    const color = emotionColor(e.emotion);
    c.setAttribute("role", "button"); c.tabIndex = 0;
    c.innerHTML = `
      <div class="entry-day">${new Date(e.timestamp).getDate().toString().padStart(2,"0")}<small>${new Date(e.timestamp).toLocaleDateString([], {weekday:"short"})}</small></div>
      <div class="row">
        <span class="date">${fmtDate(e.timestamp)}</span>
        <span class="emo-pill"><span class="dot" style="background:${color}"></span>${e.emotion || "neutral"} · ${e.intensity || 5}/10 estimated</span>
        ${e.word_count ? `<span class="badge">${e.word_count} words</span>` : ""}
      </div>
      <div class="title">${escapeHtml(e.title || e.summary || "Untitled")}</div>
      <div class="snippet">${escapeHtml((e.text || "").slice(0, 280))}</div>
      ${tags ? `<div class="tags">${tags}</div>` : ""}
    `;
    c.addEventListener("click", () => openEntry(e));
    host.appendChild(c);
  });
}

$("search-input").addEventListener("input", () => renderEntries());

// =========================================================================
// ENTRY MODAL (view / edit)
// =========================================================================
let activeEntry = null;
let editingEntry = false;

function openEntry(e) {
  activeEntry = e; editingEntry = false;
  $("modal-title").textContent = e.title || e.summary || "Entry";
  const color = emotionColor(e.emotion);
  $("modal-meta").innerHTML = `
    <span>${fmtDate(e.timestamp)}</span>
    <span style="display:inline-flex;align-items:center;gap:6px;"><span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block;"></span>${e.emotion || "neutral"} · ${e.intensity || 5}/10 estimated</span>
    ${e.user_mood != null ? `<span>Your intensity rating: ${e.user_mood}/10</span>` : ""}
    ${e.word_count ? `<span>${e.word_count} words</span>` : ""}
    ${e.tags?.length ? `<span>${e.tags.map(t => `#${escapeHtml(t)}`).join(" ")}</span>` : ""}
  `;
  $("modal-body").className = "body";
  $("modal-body").contentEditable = "false";
  $("modal-body").textContent = e.text || "";
  $("modal-reflect").innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Tap "Questions" below to receive three open prompts about this entry.</div>`;
  $("modal-connections").innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Tap "Connections" below to find related past entries.</div>`;
  $("modal-edit").textContent = "Edit";
  $("entry-modal").classList.add("active");
}

$("modal-close").addEventListener("click", closeModal);
$("modal-dismiss").addEventListener("click", closeModal);
$("entry-modal").addEventListener("click", (ev) => { if (ev.target.id === "entry-modal") closeModal(); });

function closeModal() { $("entry-modal").classList.remove("active"); activeEntry = null; editingEntry = false; }

$("modal-delete").addEventListener("click", async () => {
  if (!activeEntry) return;
  if (!confirm("Delete this entry permanently?")) return;
  try {
    await api(`/journal/${activeEntry.id}`, { method: "DELETE" });
    toast("Entry deleted"); closeModal(); loadEntries(); updateStreak();
  } catch { toast("Couldn't delete.", "error"); }
});

$("modal-edit").addEventListener("click", async () => {
  if (!activeEntry) return;
  if (!editingEntry) {
    const body = $("modal-body");
    body.className = "body editing";
    body.contentEditable = "true";
    body.focus();
    $("modal-edit").textContent = "Save";
    editingEntry = true;
  } else {
    const body = $("modal-body");
    const newText = body.innerText.trim();
    body.contentEditable = "false";
    body.className = "body";
    $("modal-edit").textContent = "Saving…";
    try {
      const r = await api(`/journal/${activeEntry.id}`, { method: "PUT", body: JSON.stringify({ text: newText }) });
      activeEntry = r.entry;
      toast("Entry updated");
      loadEntries(); updateStreak();
      openEntry(activeEntry);
    } catch { toast("Couldn't save edit.", "error"); }
    editingEntry = false;
    $("modal-edit").textContent = "Edit";
  }
});

$("modal-generate").addEventListener("click", async () => {
  if (!activeEntry) return;
  const host = $("modal-reflect");
  host.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Generating questions…</div>`;
  try {
    const r = await api(`/reflect/${activeEntry.id}`);
    const qs = r.questions || [];
    if (!qs.length) { host.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">No questions generated.</div>`; return; }
    const saved = activeEntry.reflections || [];
    host.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:14px;">
        ${qs.map((q, i) => `
          <div data-idx="${i}">
            <div class="reflect-q">${escapeHtml(q)}</div>
            <textarea class="reflect-answer input" rows="2" placeholder="Write your answer…" style="margin-top:8px;width:100%;resize:vertical;font-size:13px;line-height:1.6;box-sizing:border-box;">${escapeHtml(saved[i]?.answer || "")}</textarea>
          </div>`).join("")}
        <div style="display:flex;gap:8px;margin-top:4px;">
          <button class="btn btn-primary" id="reflect-save-btn" style="flex:1;">Save answers</button>
          <button class="btn" id="reflect-chat-btn">Discuss in chat</button>
        </div>
      </div>`;
    host.querySelector("#reflect-save-btn").addEventListener("click", async () => {
      const pairs = qs.map((q, i) => ({ question: q, answer: host.querySelectorAll(".reflect-answer")[i].value.trim() }));
      try {
        await api(`/reflect/${activeEntry.id}/answers`, { method: "POST", body: JSON.stringify({ answers: pairs }) });
        activeEntry.reflections = pairs;
        toast("Answers saved.");
      } catch { toast("Couldn't save answers.", "error"); }
    });
    host.querySelector("#reflect-chat-btn").addEventListener("click", () => {
      const pairs = qs.map((q, i) => ({ q, a: host.querySelectorAll(".reflect-answer")[i].value.trim() })).filter(p => p.a);
      const msg = pairs.length
        ? `I reflected on my entry "${activeEntry.title || "untitled"}":\n` + pairs.map(p => `Q: ${p.q}\nA: ${p.a}`).join("\n\n")
        : `I want to talk about my entry "${activeEntry.title || "untitled"}". The questions were: ${qs.join(" | ")}`;
      closeModal();
      switchView("chat");
      setTimeout(() => sendChat(msg), 150);
    });
  } catch { host.innerHTML = `<div style="color:var(--danger);font-size:13px;">Couldn't reach model.</div>`; }
});

$("modal-connections-btn").addEventListener("click", async () => {
  if (!activeEntry) return;
  const host = $("modal-connections");
  host.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Finding echoes…</div>`;
  try {
    const r = await api(`/connections/${activeEntry.id}`);
    const rel = r.related || [];
    if (!rel.length) { host.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Nothing closely related yet.</div>`; return; }
    host.innerHTML = rel.map(e => `
      <div class="related-item" data-id="${e.id}">
        <span class="dot" style="background:${emotionColor(e.emotion)}"></span>
        <span class="title">${escapeHtml(e.title || "Untitled")}</span>
        <span class="date">${e.date}</span>
      </div>`).join("");
    host.querySelectorAll(".related-item").forEach(el => el.addEventListener("click", async () => {
      const id = el.getAttribute("data-id");
      try { const ent = await api(`/journal/${id}`); openEntry(ent); } catch {}
    }));
  } catch { host.innerHTML = `<div style="color:var(--danger);font-size:13px;">Couldn't reach model.</div>`; }
});

// =========================================================================
// CHAT
// =========================================================================
const chatFeed = $("chat-feed");
const chatInput = $("chat-input");
let chatHistoryLoaded = false;

// --- mode + personality state (persisted) ----------------------------------
const PERSONA_ALIASES = {
  honest_coach: "challenger",
  calm_therapist: "companion",
  analytical_observer: "observer",
};
// Chat is always journal mode now — the General toggle served no purpose
// for a journal app. Kept the `chatMode` variable so existing call sites
// keep working without changing every fetch payload.
const chatMode = "journal";
let chatPersona = localStorage.getItem("innerbloom.chatPersona") || "companion";
if (PERSONA_ALIASES[chatPersona]) chatPersona = PERSONA_ALIASES[chatPersona];

function applyPersona() {
  $$(".persona-pill").forEach(b => {
    b.classList.toggle("active", b.dataset.persona === chatPersona);
    b.setAttribute("aria-checked", b.dataset.persona === chatPersona ? "true" : "false");
  });
}
$$(".persona-pill").forEach(b => {
  b.addEventListener("click", () => {
    chatPersona = b.dataset.persona;
    localStorage.setItem("innerbloom.chatPersona", chatPersona);
    applyPersona();
  });
});
applyPersona();

// --- scroll stickiness -----------------------------------------------------
// Auto-scroll only when the user is already pinned near the bottom. If they
// scrolled up to read something, leave them alone — no smooth animation,
// no surprise yanks.
const NEAR_BOTTOM_PX = 80;
function isNearBottom() {
  return chatFeed.scrollHeight - chatFeed.scrollTop - chatFeed.clientHeight < NEAR_BOTTOM_PX;
}
function pinToBottom(force) {
  if (force || isNearBottom()) chatFeed.scrollTop = chatFeed.scrollHeight;
}

// --- minimal markdown renderer (safe-by-default) ---------------------------
// We escape first, then re-introduce a small subset of markdown. No raw HTML
// from the model is ever inserted.
function renderMarkdown(src) {
  if (!src) return "";
  let s = escapeHtml(src);

  // Fenced code blocks ```lang\n...\n```
  s = s.replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code>${code.replace(/\n$/, "")}</code></pre>`);

  // Inline code `x`
  s = s.replace(/`([^`\n]+)`/g, "<code>$1</code>");

  // Bold **x** and italic *x* / _x_
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/(^|\W)_([^_\n]+)_(?=\W|$)/g, "$1<em>$2</em>");

  // Links [text](url) — only http(s)
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

  // Headings #, ##, ###
  s = s.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
  s = s.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");

  // Lists — group consecutive `- ` or `* ` lines into <ul>
  s = s.replace(/(?:^|\n)((?:[-*] .+(?:\n|$))+)/g, (_, block) => {
    const items = block.trim().split(/\n/).map(l =>
      `<li>${l.replace(/^[-*]\s+/, "")}</li>`).join("");
    return `\n<ul>${items}</ul>`;
  });

  // Paragraphs — split on blank lines, but skip lines already wrapped in
  // a block element so we don't double-wrap.
  const blocks = s.split(/\n{2,}/).map(b => {
    if (/^\s*<(?:h[1-3]|ul|ol|pre)/.test(b)) return b;
    return `<p>${b.replace(/\n/g, "<br>")}</p>`;
  });
  return blocks.join("\n");
}

function setMsgMarkdown(div, text) {
  // Container we can safely overwrite without nuking citation/safety rows
  let host = div.querySelector(".md");
  if (!host) {
    host = document.createElement("div");
    host.className = "md";
    div.prepend(host);
  }
  host.innerHTML = renderMarkdown(text);
}

// --- citation row ----------------------------------------------------------
function buildCiteRow(citations) {
  const row = document.createElement("div");
  row.className = "cite-row";
  citations.forEach(c => {
    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = "cite-pill";
    pill.innerHTML = `<span class="dot" style="background:${emotionColor(c.emotion)}"></span><time>${escapeHtml(c.date)}</time><span>${escapeHtml(c.title)}</span><i aria-hidden="true">↗</i>`;
    pill.title = c.title || "";
    pill.addEventListener("click", async () => {
      try { const ent = await api(`/journal/${c.id}`); openEntry(ent); } catch {}
    });
    row.appendChild(pill);
  });
  return row;
}

// --- safety card -----------------------------------------------------------
function buildSafetyCard(safety) {
  const card = document.createElement("div");
  card.className = "safety-card" + (safety.level === "soft" ? " soft" : "");
  const title = safety.level === "high" ? "I'm here — please read this" : "Just so you know";
  const resources = (safety.resources || []).map(r =>
    `<div class="resource"><span class="name">${escapeHtml(r.name)}</span><span class="detail">${escapeHtml(r.detail)}</span></div>`
  ).join("");
  card.innerHTML = `
    <div class="title">${title}</div>
    <div class="body">${escapeHtml(safety.message || "")}</div>
    <div class="resources">${resources}</div>
  `;
  return card;
}

// --- message append --------------------------------------------------------
async function loadChatHistory() {
  if (chatHistoryLoaded) return;
  try {
    const r = await api("/chat");
    const msgs = (r.messages || []);
    if (!msgs.length) return;
    $("chat-welcome")?.remove();
    msgs.forEach(m => {
      addMsg("user", m.user, [], { silent: true });
      addMsg("ai", m.ai, m.citations || [], { silent: true, safety: m.safety });
    });
    pinToBottom(true);
    chatHistoryLoaded = true;
  } catch {}
}

function addMsg(role, text, citations, opts) {
  opts = opts || {};
  $("chat-welcome")?.remove();

  if (role === "ai" && opts.safety) {
    chatFeed.appendChild(buildSafetyCard(opts.safety));
  }

  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "ai") {
    setMsgMarkdown(div, text || "");
  } else {
    div.textContent = text;
  }
  if (role === "ai" && citations && citations.length) {
    div.appendChild(buildCiteRow(citations));
  }
  chatFeed.appendChild(div);
  if (!opts.silent) pinToBottom(true);
  return div;
}

// --- agent step host -------------------------------------------------------
function buildAgentSteps() {
  const wrap = document.createElement("div");
  wrap.className = "agent-steps";
  // Toggle row, hidden until at least one real step lands.
  const summary = document.createElement("div");
  summary.className = "agent-step summary";
  summary.textContent = "Agent steps";
  summary.style.display = "none";
  summary.addEventListener("click", () => wrap.classList.toggle("collapsed"));
  wrap.appendChild(summary);
  wrap._summary = summary;
  wrap._byId = new Map();
  return wrap;
}
function upsertStep(wrap, ev) {
  let el = wrap._byId.get(ev.id);
  if (!el) {
    el = document.createElement("div");
    el.className = "agent-step";
    el.innerHTML = `<span class="icon"></span><span class="label"></span><span class="detail"></span>`;
    wrap.appendChild(el);
    wrap._byId.set(ev.id, el);
    wrap._summary.style.display = "";
  }
  el.classList.toggle("running", ev.status === "running");
  el.classList.toggle("done", ev.status === "done");
  el.querySelector(".label").textContent = ev.label || "";
  el.querySelector(".detail").textContent = ev.detail || "";
}
function collapseAgentSteps(wrap) {
  // Once the reply lands, fold the steps so the chat stays clean.
  if (wrap && wrap._byId && wrap._byId.size > 0) wrap.classList.add("collapsed");
}

// --- main send dispatcher --------------------------------------------------
async function sendChat(text) {
  if (!text.trim()) return;
  addMsg("user", text);
  chatInput.value = ""; chatInput.style.height = "auto";

  // Always runs the agent loop with live steps. Journal context is built
  // in; the LLM classifier on the backend decides whether to actually
  // pull from it for any given message.
  return sendChatAgent(text);
}

// --- general-mode: simple streamed reply ----------------------------------
async function sendChatStream(text) {
  const typing = document.createElement("div");
  typing.className = "msg ai";
  typing.innerHTML = `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>`;
  chatFeed.appendChild(typing);
  pinToBottom(true);

  let safetyCard = null;

  try {
    const resp = await fetch(API + "/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, mode: "general", personality: chatPersona }),
    });
    if (!resp.body) throw new Error("no stream");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let full = "", buffer = "", first = true, candidates = [], lastRender = 0;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      if (buffer.includes("\x1e")) {
        const idx = buffer.indexOf("\x1e");
        const nl = buffer.indexOf("\n", idx);
        if (nl > -1) {
          try {
            const obj = JSON.parse(buffer.slice(idx + 1, nl));
            if (obj.type === "manifest") {
              candidates = obj.candidates || [];
              if (obj.safety && !safetyCard) {
                safetyCard = buildSafetyCard(obj.safety);
                chatFeed.insertBefore(safetyCard, typing);
                pinToBottom(false);
              }
            }
          } catch {}
          buffer = buffer.slice(nl + 1);
        } else { continue; }
      }

      if (first && buffer) { typing.innerHTML = ""; first = false; }
      full = buffer;
      // During streaming, write plain text only — re-rendering markdown
      // on every chunk caused a flicker that read like a "page reload".
      // We format properly once on done.
      let host = typing.querySelector(".md");
      if (!host) {
        host = document.createElement("div");
        host.className = "md";
        typing.prepend(host);
      }
      host.textContent = full.replace(/\[cite:[^\]]+\]/gi, "");
      pinToBottom(false);
    }

    finalizeAiMessage(typing, full, candidates);
  } catch {
    try {
      const r = await api("/chat", {
        method: "POST",
        body: JSON.stringify({ message: text, mode: "general", personality: chatPersona }),
      });
      typing.innerHTML = "";
      setMsgMarkdown(typing, r.reply || "(no reply)");
      if (r.safety && !safetyCard) chatFeed.insertBefore(buildSafetyCard(r.safety), typing);
    } catch (err) {
      typing.textContent = `Couldn't reach the model. ${err?.message ? "(" + err.message + ")" : "Is Ollama running?"}`;
      typing.style.borderColor = "var(--danger)";
    }
  }
}

// Final pass on a streamed AI bubble: strip cite tokens, attach pills.
// Matches the broad cite shapes the model emits in practice:
//   [cite:abc]   [cite:id=abc]   [cite:id=abc, def]
function finalizeAiMessage(host, fullText, candidates) {
  const cites = [];
  // Pull every id-like alnum/hyphen run out of any [cite:...] bracket.
  const blobRx = /\[cite:[^\]]+\]/gi;
  const idRx   = /[a-f0-9\-]{4,36}/gi;
  for (const blob of fullText.match(blobRx) || []) {
    for (const sid of blob.match(idRx) || []) {
      const norm = sid.toLowerCase();
      const c = (candidates || []).find(c =>
        c.id === norm || c.full_id === norm ||
        String(c.id || "").toLowerCase() === norm ||
        String(c.full_id || "").toLowerCase() === norm
      );
      if (c && !cites.find(x => x.id === (c.full_id || c.id))) {
        cites.push({ id: c.full_id || c.id, title: c.title, date: c.date, emotion: c.emotion });
      }
    }
  }
  // Strip every [cite:...] block + clean up any empty parens left behind.
  let cleaned = fullText.replace(/\s*[\(\[]?\s*\[cite:[^\]]+\]\s*[\)\]]?/gi, " ");
  cleaned = cleaned.replace(/\(\s*\)/g, "").replace(/\s{2,}/g, " ").replace(/\s+([.,;:!?])/g, "$1").trim();
  if (!cleaned) cleaned = "(no reply)";
  host.innerHTML = "";
  setMsgMarkdown(host, cleaned);
  if (cites.length) host.appendChild(buildCiteRow(cites));
  pinToBottom(false);
}

// --- journal-mode: agent loop with live steps -----------------------------
async function sendChatAgent(text) {
  const stepsHost = buildAgentSteps();
  chatFeed.appendChild(stepsHost);

  const typing = document.createElement("div");
  typing.className = "msg ai";
  typing.innerHTML = `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>`;
  chatFeed.appendChild(typing);
  pinToBottom(true);

  let safetyCard = null;
  let candidates = [];
  let full = "";
  let firstToken = true;
  let lastRender = 0;

  try {
    const resp = await fetch(API + "/chat/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, mode: "journal", personality: chatPersona }),
    });
    if (!resp.body) throw new Error("no stream");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let nl;
      while ((nl = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        let ev;
        try { ev = JSON.parse(line); } catch { continue; }

        switch (ev.type) {
          case "safety":
            if (ev.safety && !safetyCard) {
              safetyCard = buildSafetyCard(ev.safety);
              chatFeed.insertBefore(safetyCard, stepsHost);
              pinToBottom(false);
            }
            break;
          case "step":
            upsertStep(stepsHost, ev);
            pinToBottom(false);
            break;
          case "manifest":
            candidates = ev.candidates || [];
            break;
          case "token": {
            if (firstToken) { typing.innerHTML = ""; firstToken = false; }
            full += ev.value || "";
            // Plain text during the stream — markdown is rendered once on
            // 'done'. Re-running the markdown regex per chunk caused a
            // flicker that felt like the page was reloading.
            let host = typing.querySelector(".md");
            if (!host) {
              host = document.createElement("div");
              host.className = "md";
              typing.prepend(host);
            }
            host.textContent = full.replace(/\[cite:[^\]]+\]/gi, "");
            pinToBottom(false);
            break;
          }
          case "done":
            finalizeAiMessage(typing, full, candidates);
            collapseAgentSteps(stepsHost);
            break;
        }
      }
    }
    // If stream ended without an explicit "done", still finalize.
    if (firstToken === false) finalizeAiMessage(typing, full, candidates);
    collapseAgentSteps(stepsHost);
  } catch (err) {
    typing.textContent = `Couldn't reach the model. ${err?.message ? "(" + err.message + ")" : "Is Ollama running?"}`;
    typing.style.borderColor = "var(--danger)";
  }
}

$("chat-send").addEventListener("click", () => sendChat(chatInput.value));
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(chatInput.value); }
});
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + "px";
});
$$(".suggest").forEach(s => s.addEventListener("click", () => sendChat(s.getAttribute("data-q"))));

// =========================================================================
// INSIGHTS
// =========================================================================
async function loadInsights() {
  try {
    const s = await api("/stats");
    renderStats(s);
    renderDailyChart(s.daily);
    renderHeatmap(s.heatmap);
    renderEmotionBars(s.emotions);
    renderTagCloud(s.top_tags);
    document.dispatchEvent(new CustomEvent("innerbloom:stats", { detail: s }));
  } catch {
    $("stat-grid").innerHTML = `<div class="empty"><h3>Your journal is offline</h3><p>Start the local app to see your patterns.</p></div>`;
  }
}

function renderStats(s) {
  $("stat-grid").innerHTML = `
    <div class="stat-card">
      <div class="label">Entries</div>
      <div class="value">${s.total_entries}</div>
      <div class="sub">all time</div>
    </div>
    <div class="stat-card">
      <div class="label">Words written</div>
      <div class="value">${s.total_words.toLocaleString()}</div>
      <div class="sub">avg ${s.avg_words} / entry</div>
    </div>
    <div class="stat-card">
      <div class="label">Current streak</div>
      <div class="value">${s.streak_current}<span class="unit">${s.streak_current === 1 ? "day" : "days"}</span></div>
      <div class="sub">longest ${s.streak_longest} days</div>
    </div>
    <div class="stat-card">
      <div class="label">Top emotion</div>
      <div class="value" style="font-size:22px;text-transform:capitalize;">${s.emotions?.[0]?.[0] || "—"}</div>
      <div class="sub">${s.emotions?.[0]?.[1] || 0} entries</div>
    </div>
  `;
}

let lastChartData = [];
function renderDailyChart(daily) {
  lastChartData=daily||[];
  const wrap=$("mood-line-wrap"),canvas=$("mood-line-canvas");
  canvas.hidden=true;$("chart-axis").hidden=true;
  let host=$("daily-rhythm");
  if(!host){host=document.createElement('div');host.id='daily-rhythm';wrap.append(host);}
  const observed=lastChartData.filter(d=>d.avg_intensity!=null);
  if(!observed.length){host.innerHTML='<p class="rhythm-empty">A little writing, a little perspective.<br>Your daily rhythm will appear here.</p>';$("mood-week-compare").innerHTML='';return;}
  host.innerHTML=`<div class="rhythm-scale"><span>INTENSITY / 10</span><span>${fmtDateShort(lastChartData[0].date)} — ${fmtDateShort(lastChartData.at(-1).date)}</span></div><div class="rhythm-stems" role="group" aria-label="Daily emotional intensity">${lastChartData.map((d,i)=>`<button class="rhythm-day ${d.avg_intensity==null?'unwritten':''}" style="--level:${d.avg_intensity==null?0:(d.avg_intensity/10*100)}%" data-day="${i}" aria-pressed="false" aria-label="${fmtDateShort(d.date)}, ${d.avg_intensity==null?'no entries':d.avg_intensity+' out of 10, '+d.count+' entries'}"><span class="stem-track"><span class="stem-fill"></span></span><small>${new Date(d.date+'T12:00:00').getDate()}</small></button>`).join('')}</div><div class="rhythm-detail" aria-live="polite"></div>`;
  function select(i){const d=lastChartData[i];host.querySelectorAll('[data-day]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.day)===i)));host.querySelector('.rhythm-detail').innerHTML=`<div><span class="eyebrow">${escapeHtml(fmtDateShort(d.date))}</span><strong>${d.avg_intensity==null?'A quiet space':d.avg_intensity+' <small>/ 10</small>'}</strong></div><p>${d.avg_intensity==null?'No entry on this day.':d.count+' '+(d.count===1?'entry':'entries')+' · model-estimated intensity'}</p>${d.count?'<button class="text-action">Read this day ↗</button>':''}`;host.querySelector('.rhythm-detail button')?.addEventListener('click',()=>openArchiveDay(d.date));}
  host.querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>select(Number(b.dataset.day)));
  select(lastChartData.findLastIndex(d=>d.avg_intensity!=null));
  const week=lastChartData.slice(-7),previous=lastChartData.slice(-14,-7);
  const avg=ds=>{const ps=ds.filter(d=>d.avg_intensity!=null);return ps.length?(ps.reduce((a,d)=>a+d.avg_intensity,0)/ps.length).toFixed(1):'—'};
  $("mood-week-compare").innerHTML=`<div><span class="eyebrow">THIS WEEK</span><strong>${avg(week)} <small>/ 10</small></strong><span>${avg(previous)} in the previous week</span></div><div><span class="eyebrow">MOMENTS KEPT</span><strong>${week.reduce((a,d)=>a+d.count,0)}</strong><span>Across the last seven days</span></div>`;
}
function openArchiveDay(date){window.innerbloomDateFilter=date;document.dispatchEvent(new CustomEvent('innerbloom:archive-date',{detail:date}));currentEmotionFilter=null;$("search-input").value='';switchView('entries');}


function heatColor(count) {
  if (!count) return "rgba(219,94,18,0.07)";
  if (count === 1) return "rgba(227,114,38,0.28)";
  if (count === 2) return "rgba(227,114,38,0.52)";
  if (count === 3) return "rgba(227,114,38,0.76)";
  return "#b95116";
}

let writingMonth = null;
function renderHeatmap(heatmap) {
  const host=$("heatmap");host.className='writing-calendar';
  if(!heatmap?.length){host.innerHTML='<p>Your writing history starts with your first entry.</p>';return;}
  const available=[...new Set(heatmap.map(d=>d.date.slice(0,7)))];
  if(!writingMonth||!available.includes(writingMonth))writingMonth=available.at(-1);
  const days=heatmap.filter(d=>d.date.startsWith(writingMonth)), date=new Date(writingMonth+'-01T12:00:00');
  const index=available.indexOf(writingMonth),first=(date.getDay()+6)%7, count=new Date(date.getFullYear(),date.getMonth()+1,0).getDate();
  const lookup=new Map(days.map(d=>[Number(d.date.slice(-2)),d]));
  host.innerHTML=`<div class="month-story"><span class="eyebrow">YOUR WRITING DAYS</span><h3>${date.toLocaleDateString([], {month:'long'})}<small>${date.getFullYear()}</small></h3><div class="month-totals"><strong>${days.filter(d=>d.count).length}<span>days you made space</span></strong><strong>${days.reduce((a,d)=>a+d.count,0)}<span>moments kept</span></strong></div><p>Some days call for a page.<br>Others, just a pause.</p><div class="month-pager"><button class="btn" id="writing-prev" aria-label="Previous writing month" ${index===0?'disabled':''}>←</button><span>${index+1} / ${available.length}</span><button class="btn" id="writing-next" aria-label="Next writing month" ${index===available.length-1?'disabled':''}>→</button></div></div><div class="month-sheet"><div class="month-weekdays">${['M','T','W','T','F','S','S'].map(d=>`<span>${d}</span>`).join('')}</div><div class="month-days">${'<span></span>'.repeat(first)}${Array.from({length:count},(_,i)=>{const d=lookup.get(i+1);return `<button class="writing-day ${d?.count?'written':''}" ${!d?.count?'disabled':''} data-date="${d?.date||''}" aria-label="${date.toLocaleDateString([],{month:'long'})} ${i+1}, ${d?.count||0} entries"><span>${i+1}</span><i>${d?.count?String(d.count).padStart(2,'0'):''}</i></button>`}).join('')}</div><p class="calendar-key"><i></i> A day with a story · select to read</p></div>`;
  host.querySelectorAll('[data-date]:not(:disabled)').forEach(b=>b.onclick=()=>openArchiveDay(b.dataset.date));
  $("writing-prev").onclick=()=>{writingMonth=available[index-1];renderHeatmap(heatmap)};
  $("writing-next").onclick=()=>{writingMonth=available[index+1];renderHeatmap(heatmap)};
}

function renderEmotionBars(emotions) {
  const host=$("emotion-bars"); const total=emotions.reduce((a,[,n])=>a+n,0);
  host.innerHTML=emotions.length?`<div class="feeling-segments" aria-hidden="true">${emotions.map(([e,n])=>`<span style="flex:${n};background:${emotionColor(e)}"></span>`).join('')}</div><div class="feeling-ledger">${emotions.slice(0,8).map(([e,n])=>`<div><span class="feeling-mark" style="--feeling:${emotionColor(e)}"></span><span>${escapeHtml(e)}</span><strong>${Math.round(n/total*100)}<small>%</small></strong><small>${n} entries</small></div>`).join('')}</div>`:'<p>Your feelings will find their place here.</p>';
}
function renderTagCloud(tags) {
  const host=$("tag-cloud");host.className='topic-ledger';host.innerHTML='';
  tags.forEach(([tag,count],i)=>{const b=document.createElement('button');b.innerHTML=`<small>${String(i+1).padStart(2,'0')}</small><span>${escapeHtml(tag)}</span><small>${count} entries</small><span>↗</span>`;b.onclick=()=>{window.innerbloomDateFilter=null;currentEmotionFilter=null;$("search-input").value=tag;switchView('entries')};host.append(b)});
  if(!tags.length)host.innerHTML='<p>Topics emerge as you write.</p>';
}

async function runAnalysis(path, label) {
  const box = $("analysis-box");
  box.classList.add("loading");
  box.textContent = `${label}… (20-60s on low RAM)`;
  try {
    const r = await api(path);
    box.classList.remove("loading");
    box.innerHTML = mdToHtml(r.result || "(nothing returned)");
  } catch {
    box.classList.remove("loading");
    box.textContent = "Couldn't reach the model.";
  }
}
$("btn-analyze").addEventListener("click", () => runAnalysis("/analyze", "Reading 40 recent entries"));
$("btn-weekly").addEventListener("click", () => runAnalysis("/weekly-review", "Reviewing last 7 days"));
$("btn-monthly").addEventListener("click", () => runAnalysis("/monthly-review", "Reflecting on 30 days"));

// --- Contradictions (Phase 3 insight engine) ------------------------------
// Reveal pattern: cap visible items, show "Show all (N)" toggle when there
// are more. Keeps the page from feeling cluttered while still giving access
// to the long tail.
const CONTRADICTIONS_DEFAULT_LIMIT = 3;
let _contradictionsExpanded = false;

function renderContradictions(data) {
  const list = $("contradiction-list");
  const meta = $("contradictions-meta");
  const items = (data && data.items) || [];

  if (data && data.generated_at) {
    const when = new Date(data.generated_at).toLocaleString();
    meta.textContent = `${items.length} found · last run ${when}`;
  } else {
    meta.textContent = "";
  }

  if (!items.length) {
    list.innerHTML = `<div class="contradictions-empty">${
      data && data.generated_at
        ? (data.note || "No clear contradictions found in the recent window. That's a real signal too.")
        : "Click \"Find contradictions\" to scan your last 60 days for gaps between what you say and what you do."
    }</div>`;
    return;
  }

  const visible = _contradictionsExpanded ? items : items.slice(0, CONTRADICTIONS_DEFAULT_LIMIT);
  const hiddenCount = items.length - visible.length;

  list.innerHTML = "";
  visible.forEach(c => {
    const card = document.createElement("div");
    card.className = "contradiction-card";

    const head = document.createElement("div");
    head.className = "head";
    head.innerHTML = `
      <span class="pattern-tag">${escapeHtml(c.pattern || "pattern")}</span>
      <span class="sev ${c.severity || "medium"}">${c.severity || "medium"}</span>
    `;
    card.appendChild(head);

    const pair = document.createElement("div");
    pair.className = "pair";
    pair.innerHTML = `
      <div class="line stated"><span class="marker">You say</span><span>${escapeHtml(c.stated)}</span></div>
      <div class="line behavior"><span class="marker">But</span><span>${escapeHtml(c.behavior)}</span></div>
    `;
    card.appendChild(pair);

    if (c.evidence && c.evidence.length) {
      card.appendChild(buildCiteRow(c.evidence));
    }
    if (c.honest_note) {
      const note = document.createElement("div");
      note.className = "note";
      note.textContent = c.honest_note;
      card.appendChild(note);
    }
    list.appendChild(card);
  });

  if (hiddenCount > 0 || _contradictionsExpanded) {
    const more = document.createElement("button");
    more.className = "show-more-btn";
    more.type = "button";
    more.textContent = _contradictionsExpanded
      ? "Show fewer"
      : `Show all ${items.length} contradictions`;
    more.addEventListener("click", () => {
      _contradictionsExpanded = !_contradictionsExpanded;
      renderContradictions(data);
    });
    list.appendChild(more);
  }
}

async function loadContradictions() {
  try {
    const data = await api("/insights/contradictions");
    renderContradictions(data);
  } catch {
    $("contradiction-list").innerHTML = `<div class="contradictions-empty">Couldn't reach the backend.</div>`;
  }
}

$("btn-contradictions-refresh").addEventListener("click", async () => {
  // Async: backend runs in a background thread. Topbar polling shows
  // progress; this card refreshes itself when the engine finishes.
  const list = $("contradiction-list");
  list.innerHTML = `<div class="contradictions-empty">Started a refresh in the background — the card will update when it's done.</div>`;
  try { await api("/insights/contradictions/refresh", { method: "POST" }); }
  catch { list.innerHTML = `<div class="contradictions-empty">Couldn't start the scan. Is Ollama running?</div>`; }
});

// --- Emotional Triggers (Phase 3 insight engine) -------------------------
const TRIGGERS_DEFAULT_LIMIT = 4;
let _triggersExpanded = false;

function renderTriggers(data) {
  const grid = $("trigger-grid");
  const meta = $("triggers-meta");
  const items = (data && data.items) || [];

  if (data && data.generated_at) {
    const when = new Date(data.generated_at).toLocaleString();
    meta.textContent = `${items.length} found · last run ${when}`;
  } else {
    meta.textContent = "";
  }

  if (!items.length) {
    grid.innerHTML = `<div class="triggers-empty">${
      data && data.generated_at
        ? (data.note || "No strong triggers stand out yet — your moods are pretty even across topics.")
        : "Click \"Map triggers\" to find what consistently lifts or drains your mood across the last 90 days."
    }</div>`;
    return;
  }

  // Map signed delta into a 0–50% width on the half-bar (each side caps at 50%).
  const widthForDelta = d => `${Math.min(50, Math.abs(d) * 6)}%`;

  const visible = _triggersExpanded ? items : items.slice(0, TRIGGERS_DEFAULT_LIMIT);
  const hiddenCount = items.length - visible.length;

  grid.innerHTML = "";
  visible.forEach(t => {
    const card = document.createElement("div");
    card.className = `trigger-card ${t.direction}`;

    const stats = t.stats || {};
    const dirArrow = t.direction === "negative" ? "↓" : "↑";
    const dirLabel = t.direction === "negative" ? "drains" : "lifts";
    const freq = stats.frequency != null ? `${stats.frequency} entries` : "";

    const head = document.createElement("div");
    head.className = "head";
    head.innerHTML = `
      <span class="cat">${escapeHtml(t.category || "other")}</span>
      <span class="dir">${dirArrow} ${dirLabel}</span>
      ${freq ? `<span class="freq">· ${escapeHtml(freq)}</span>` : ""}
    `;
    card.appendChild(head);

    const title = document.createElement("div");
    title.className = "title";
    title.innerHTML = `${escapeHtml(t.label)}${
      t.outcome ? `<span class="arrow">→</span><span class="outcome">${escapeHtml(t.outcome)}</span>` : ""
    }`;
    card.appendChild(title);

    if (stats.delta != null) {
      const sign = stats.delta >= 0 ? "+" : "";
      const statRow = document.createElement("div");
      statRow.className = "stats";
      statRow.innerHTML = `
        <span class="delta">${sign}${stats.delta.toFixed(1)}</span>
        <div class="bar">
          <div class="axis"></div>
          <div class="fill" style="${t.direction === "negative" ? "width" : "width"}:${widthForDelta(stats.delta)}"></div>
        </div>
        <span>vs your baseline</span>
      `;
      card.appendChild(statRow);
    }

    if (t.evidence && t.evidence.length) {
      card.appendChild(buildCiteRow(t.evidence));
    }
    if (t.pattern_note) {
      const note = document.createElement("div");
      note.className = "note";
      note.textContent = t.pattern_note;
      card.appendChild(note);
    }
    grid.appendChild(card);
  });

  if (hiddenCount > 0 || _triggersExpanded) {
    const more = document.createElement("button");
    more.className = "show-more-btn show-more-btn--grid";
    more.type = "button";
    more.textContent = _triggersExpanded
      ? "Show fewer"
      : `Show all ${items.length} triggers`;
    more.addEventListener("click", () => {
      _triggersExpanded = !_triggersExpanded;
      renderTriggers(data);
    });
    grid.appendChild(more);
  }
}

async function loadTriggers() {
  try {
    const data = await api("/insights/triggers");
    renderTriggers(data);
  } catch {
    $("trigger-grid").innerHTML = `<div class="triggers-empty">Couldn't reach the backend.</div>`;
  }
}

$("btn-triggers-refresh").addEventListener("click", async () => {
  const grid = $("trigger-grid");
  grid.innerHTML = `<div class="triggers-empty">Started in the background — the grid will update when it's done.</div>`;
  try { await api("/insights/triggers/refresh", { method: "POST" }); }
  catch { grid.innerHTML = `<div class="triggers-empty">Couldn't start the scan. Is Ollama running?</div>`; }
});

// --- Wellbeing radar (Phase 3 insight engine) ----------------------------
function renderWellbeingCard(host, name, signal) {
  const level = (signal && signal.level) || "ok";
  host.className = `wellbeing-card ${level}`;
  host.innerHTML = `<div class="level-strip"></div>`;

  const head = document.createElement("div");
  head.className = "head";
  head.innerHTML = `<div class="name">${name}</div><div class="level">${level === "ok" ? "No pattern flagged" : escapeHtml(level)}</div>`;
  host.appendChild(head);

  // Stat row — different fields for burnout vs spiral
  const statsRow = document.createElement("div");
  statsRow.className = "stats-row";
  if (name === "Burnout") {
    if (signal.entry_count != null) statsRow.innerHTML += `<span class="stat">entries <b>${signal.entry_count}</b></span>`;
    if (signal.avg_mood != null)    statsRow.innerHTML += `<span class="stat">avg mood <b>${signal.avg_mood}</b></span>`;
    if (signal.exhaustion_count != null && signal.entry_count) statsRow.innerHTML +=
      `<span class="stat">exhaustion <b>${signal.exhaustion_count}/${signal.entry_count}</b></span>`;
    if (signal.drift != null) {
      const sign = signal.drift > 0 ? "+" : "";
      statsRow.innerHTML += `<span class="stat">drift <b>${sign}${signal.drift}</b></span>`;
    }
  } else {
    if (signal.consecutive_decline != null) statsRow.innerHTML +=
      `<span class="stat">decline <b>${signal.consecutive_decline} days</b></span>`;
    if (signal.tail_avg_mood != null) statsRow.innerHTML +=
      `<span class="stat">tail avg <b>${signal.tail_avg_mood}</b></span>`;
    if (signal.entry_count != null) statsRow.innerHTML +=
      `<span class="stat">entries <b>${signal.entry_count}</b></span>`;
  }
  if (statsRow.children.length) {const details=document.createElement("details");details.className="signal-details";details.innerHTML="<summary>What this is based on</summary>";details.append(statsRow);host.append(details);}

  const summary = document.createElement("div");
  summary.className = "summary" + (signal.summary ? "" : " muted");
  // Allow [id8] inline citations to read as plain text — pills carry the actual links
  summary.textContent = signal.summary || "No clear pattern yet.";
  host.insertBefore(summary, host.querySelector(".signal-details"));

  if (signal.evidence && signal.evidence.length) {
    const evidence=document.createElement("details");evidence.className="signal-evidence";evidence.innerHTML=`<summary>${signal.evidence.length} supporting entries</summary>`;evidence.appendChild(buildCiteRow(signal.evidence));host.appendChild(evidence);
  }
}

function renderWellbeing(data) {
  const row = $("wellbeing-row");
  const meta = $("wellbeing-meta");

  if (data && data.generated_at) {
    const when = new Date(data.generated_at).toLocaleDateString([], {month:"short",day:"numeric"});
    meta.textContent = `Updated ${when}`;
  } else {
    meta.textContent = "";
  }

  row.innerHTML = "";
  const burnoutHost = document.createElement("div");
  const spiralHost  = document.createElement("div");
  row.appendChild(burnoutHost);
  row.appendChild(spiralHost);
  renderWellbeingCard(burnoutHost, "Burnout", (data && data.burnout) || { level: "ok" });
  renderWellbeingCard(spiralHost,  "Negative spiral", (data && data.spiral) || { level: "ok" });
}

async function loadWellbeing() {
  try {
    const data = await api("/insights/wellbeing");
    renderWellbeing(data);
  } catch {
    /* leave the placeholder cards as-is */
  }
}

$("btn-wellbeing-refresh").addEventListener("click", async () => {
  try { await api("/insights/wellbeing/refresh", { method: "POST" }); }
  catch { /* badge will show running state */ }
});

// --- Identity & Narrative (Phase 3 insight engine) -----------------------
function renderNarrative(data) {
  const host = $("narrative-host");
  const meta = $("narrative-meta");

  if (data && data.generated_at) {
    meta.textContent = `last run ${new Date(data.generated_at).toLocaleString()}`;
  } else {
    meta.textContent = "";
  }

  const lines = data?.identity_lines || [];
  const arcs = data?.current_arcs || [];
  const values = data?.values_in_action || [];
  const tensions = data?.tensions || [];
  const becoming = data?.becoming || "";

  if (!lines.length && !arcs.length && !values.length && !tensions.length && !becoming) {
    host.innerHTML = `<div class="narrative-empty">${
      data && data.generated_at
        ? (data.note || "Couldn't ground a real narrative in the entries — try again with more recent writing.")
        : "Click \"Build narrative\" to generate a self-narrative from your last 120 days."
    }</div>`;
    return;
  }

  const card = document.createElement("div");
  card.className = "narrative-card";

  if (lines.length) {
    const sec = document.createElement("div"); sec.className = "narrative-section";
    sec.innerHTML = `<div class="label">Who you are, in your own words</div>`;
    const list = document.createElement("div"); list.className = "narrative-identity";
    lines.forEach(l => {
      const div = document.createElement("div");
      div.className = "line";
      div.textContent = l;
      list.appendChild(div);
    });
    sec.appendChild(list);
    card.appendChild(sec);
  }

  if (arcs.length) {
    const sec = document.createElement("div"); sec.className = "narrative-section";
    sec.innerHTML = `<div class="label">Arcs in motion</div>`;
    const grid = document.createElement("div"); grid.className = "narrative-grid";
    arcs.forEach(a => {
      const item = document.createElement("div"); item.className = "narrative-item";
      item.innerHTML = `<div class="head">${escapeHtml(a.label || "")}</div>
                        <div class="body">${escapeHtml(a.description || "")}</div>`;
      if (a.evidence?.length) item.appendChild(buildCiteRow(a.evidence));
      grid.appendChild(item);
    });
    sec.appendChild(grid);
    card.appendChild(sec);
  }

  if (values.length) {
    const sec = document.createElement("div"); sec.className = "narrative-section";
    sec.innerHTML = `<div class="label">Values, shown in action</div>`;
    const grid = document.createElement("div"); grid.className = "narrative-grid";
    values.forEach(v => {
      const item = document.createElement("div"); item.className = "narrative-item";
      item.innerHTML = `<div class="head"><span class="value-tag">${escapeHtml(v.value || "")}</span></div>
                        <div class="body">${escapeHtml(v.evidence_note || "")}</div>`;
      if (v.evidence?.length) item.appendChild(buildCiteRow(v.evidence));
      grid.appendChild(item);
    });
    sec.appendChild(grid);
    card.appendChild(sec);
  }

  if (tensions.length) {
    const sec = document.createElement("div"); sec.className = "narrative-section";
    sec.innerHTML = `<div class="label">Tensions you're holding</div>`;
    const list = document.createElement("div"); list.style.cssText = "display:flex;flex-direction:column;gap:8px;";
    tensions.forEach(t => {
      const row = document.createElement("div"); row.className = "narrative-tension";
      row.innerHTML = `<div class="a">${escapeHtml(t.a || "")}</div><div class="vs">vs</div><div class="b">${escapeHtml(t.b || "")}</div>`;
      list.appendChild(row);
      if (t.evidence?.length) {
        const ev = buildCiteRow(t.evidence);
        ev.style.marginTop = "0"; ev.style.paddingLeft = "4px";
        list.appendChild(ev);
      }
    });
    sec.appendChild(list);
    card.appendChild(sec);
  }

  if (becoming) {
    const sec = document.createElement("div"); sec.className = "narrative-section";
    sec.innerHTML = `<div class="label">What's becoming</div>`;
    const b = document.createElement("div"); b.className = "narrative-becoming";
    b.textContent = becoming;
    sec.appendChild(b);
    card.appendChild(sec);
  }

  host.innerHTML = "";
  host.appendChild(card);
}

async function loadNarrative() {
  try {
    const data = await api("/insights/narrative");
    renderNarrative(data);
  } catch {
    $("narrative-host").innerHTML = `<div class="narrative-empty">Couldn't reach the backend.</div>`;
  }
}

$("btn-narrative-refresh").addEventListener("click", async () => {
  const host = $("narrative-host");
  host.innerHTML = `<div class="narrative-empty">Started in the background — this can take 60–120 seconds. The card will update on its own.</div>`;
  try { await api("/insights/narrative/refresh", { method: "POST" }); }
  catch { host.innerHTML = `<div class="narrative-empty">Couldn't start. Is Ollama running?</div>`; }
});

// =========================================================================
// MEMORY MAP — focused spatial connections
// =========================================================================
const memoryMap={nodes:[],edges:[],selected:null,page:0};
function stopGraphSim() {} // Navigation no longer needs a continuously running simulation.
async function loadGraph(){
  const host=$("memory-explorer");host.innerHTML='<p class="empty">Finding the threads between your pages…</p>';
  try {const data=await api('/journal?limit=100000');const network=buildMemoryNetwork(data.entries||[]);memoryMap.nodes=network.nodes;memoryMap.edges=network.edges;memoryMap.total=data.total;
    if(!memoryMap.nodes.some(n=>n.id===memoryMap.selected))memoryMap.selected=memoryMap.nodes[0]?.id;
    memoryMap.page=0;
    if(!memoryMap.nodes.length){host.innerHTML='<div class="empty"><h3>One memory starts a thread.</h3><p>Write an entry, then return here to explore its connections.</p><button class="btn btn-primary" id="map-write">Write a moment ↗</button></div>';$("map-write").onclick=()=>switchView('write');return;}
    host.innerHTML=`<aside class="memory-index"><span class="eyebrow">START WITH A MEMORY</span><label class="memory-search"><span>⌕</span><input id="memory-search" placeholder="Find a moment…" aria-label="Find a memory" /></label><div id="memory-list"></div><p class="memory-count">${memoryMap.nodes.length} recent memories</p></aside><div class="memory-stage" id="memory-stage"></div>`;
    $("memory-search").oninput=renderMemoryIndex;renderMemoryIndex();renderMemoryConnections();
  }catch{host.innerHTML='<div class="empty"><h3>Your memories are unavailable.</h3><p>Check that the local app is running.</p></div>';}
}
function renderMemoryIndex(){
  const query=$("memory-search").value.toLowerCase(),host=$("memory-list");host.innerHTML='';
  host.closest('.memory-index').classList.toggle('has-query',!!query);
  memoryMap.nodes.filter(n=>[n.title,...n.tags,...n.themes].join(' ').toLowerCase().includes(query)).forEach(n=>{const b=document.createElement('button');b.className='memory-index-item';b.setAttribute('aria-pressed',String(n.id===memoryMap.selected));b.innerHTML=`<time>${escapeHtml(fmtDateShort(n.date))}</time><span>${escapeHtml(n.title||'Untitled memory')}</span><i>↗</i>`;b.onclick=()=>{memoryMap.selected=n.id;memoryMap.page=0;renderMemoryIndex();renderMemoryConnections()};host.append(b)});
  if(!host.children.length)host.innerHTML='<p class="muted">No matching memories.</p>';
}
async function openMemory(id){try{const entry=await api('/journal/'+encodeURIComponent(id));openEntry(entry.entry||entry)}catch{toast('Could not open this memory.','error')}}
function renderMemoryConnections(){
  return renderDotMemoryMap(memoryMap, $("memory-stage"));
}

// =========================================================================
// PEOPLE — who shows up in your journal, with mood crossover
// =========================================================================
async function loadPeople() {
  const host = $("people-content");
  host.innerHTML = `<div class="empty"><h3>Loading…</h3></div>`;
  try {
    const d = await api("/people");
    const people = d.people || [];
    if (!people.length) {
      host.innerHTML = `
        <div class="empty">
          <h3>No people yet</h3>
          <p>Mention someone by name in your entries — a friend, a partner, mom, your therapist — and they'll show up here with the moods that surround them.</p>
        </div>`;
      return;
    }

    const maxMentions = Math.max(1, ...people.map(p => p.mentions));
    const cards = people.map(p => {
      const emoColor = `var(--e-${p.top_emotion || "neutral"})`;
      const tags = (p.top_tags || []).slice(0, 4)
        .map(t => `<span class="anniv-tag">#${escapeHtml(t)}</span>`).join("");
      const themes = (p.top_themes || []).slice(0, 3)
        .map(t => `<span class="anniv-tag" style="background:var(--accent-soft);color:var(--accent-deep);">${escapeHtml(t)}</span>`).join("");
      // Emotion mini-bars
      const totalEmos = p.emotion_breakdown.reduce((s, [, c]) => s + c, 0) || 1;
      const emoBars = p.emotion_breakdown.slice(0, 4).map(([e, c]) => {
        const pct = Math.round((c / totalEmos) * 100);
        return `
          <div class="person-emo-row" title="${c} entries">
            <span class="dot" style="background:var(--e-${e});"></span>
            <span class="person-emo-name">${escapeHtml(e)}</span>
            <div class="person-emo-bar"><div class="person-emo-fill" style="width:${pct}%;background:var(--e-${e});"></div></div>
            <span class="person-emo-pct">${pct}%</span>
          </div>`;
      }).join("");
      // Entry pills (clickable)
      const entryPills = (p.entries || []).slice(0, 6).map(e => `
        <span class="cite-pill" data-id="${e.id}" title="${escapeHtml(e.title || "")}">
          <span class="dot" style="background:var(--e-${e.emotion || "neutral"});"></span>
          ${escapeHtml(e.date)}
        </span>`).join("");

      const sizeRatio = p.mentions / maxMentions;
      const avatarScale = 0.7 + sizeRatio * 0.5;
      const chips = peopleChips(p);
      const metaBits = [];
      if (p.mentions) metaBits.push(`<b>${p.mentions}</b> ${p.mentions === 1 ? "mention" : "mentions"}`);
      if (p.avg_intensity != null) metaBits.push(`avg ${p.avg_intensity}/10`);
      if (p.first_seen && p.last_seen) metaBits.push(`${p.first_seen} → ${p.last_seen}`);
      if (!metaBits.length) metaBits.push("no mentions yet");
      return `
        <div class="person-card" data-key="${escapeHtml(p.key)}">
          <div class="person-head">
            <div class="person-avatar" style="transform:scale(${avatarScale.toFixed(2)});background:linear-gradient(135deg, ${emoColor}, ${emoColor});">
              ${escapeHtml((p.name || "?").charAt(0).toUpperCase())}
            </div>
            <div class="person-info">
              <div class="person-name">${escapeHtml(p.name)}</div>
              <div class="person-meta">${metaBits.join(" · ")}</div>
            </div>
          </div>
          ${chips ? `<div class="person-chips">${chips}</div>` : ""}
          ${emoBars ? `<div class="person-emo-list">${emoBars}</div>` : ""}
          ${(tags + themes) ? `<div class="person-tags">${themes}${tags}</div>` : ""}
          ${entryPills ? `<div class="person-entries">${entryPills}</div>` : ""}
        </div>`;
    }).join("");

    host.innerHTML = `
      <div class="people-header">
        ${people.length} ${people.length === 1 ? "person" : "people"} in your circle.
        Click anyone to add a relationship, birthday, check-in cadence, and notes.
        Faces are coloured by their dominant emotion in your writing.
      </div>
      <div class="people-grid">${cards}</div>`;

    // Click a card → open the CRM detail drawer.
    host.querySelectorAll(".person-card[data-key]").forEach(card => {
      card.addEventListener("click", () => openPersonModal(card.getAttribute("data-key")));
    });
    // Entry pills open the entry (and shouldn't also open the person drawer).
    host.querySelectorAll(".cite-pill[data-id]").forEach(el => {
      el.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const id = el.getAttribute("data-id");
        try { const e = await api(`/journal/${id}`); openEntry(e); } catch {}
      });
    });
  } catch (e) {
    host.innerHTML = `<div class="empty"><h3>Couldn't load</h3><p>${escapeHtml(e.message)}</p></div>`;
  }
}

// Status chips shown on a person card and in the detail header.
function peopleChips(p) {
  const chips = [];
  if (p.pinned) chips.push(`<span class="person-chip pin">pinned</span>`);
  if (p.relationship) chips.push(`<span class="person-chip rel">${escapeHtml(p.relationship)}</span>`);
  if (p.overdue) {
    const d = p.days_since_last_seen != null ? ` · ${p.days_since_last_seen}d` : "";
    chips.push(`<span class="person-chip overdue">overdue${d}</span>`);
  }
  if (p.birthday_in_days != null && p.birthday_in_days <= 30) {
    const when = p.birthday_in_days === 0 ? "today" : `in ${p.birthday_in_days}d`;
    chips.push(`<span class="person-chip bday">birthday ${when}</span>`);
  }
  return chips.join("");
}

const RELATIONSHIP_OPTIONS = ["", "friend", "family", "partner", "mentor", "colleague", "other"];

const CADENCE_PRESETS = [
  { label: "Off", days: null },
  { label: "Weekly", days: 7 },
  { label: "Every 2 weeks", days: 14 },
  { label: "Monthly", days: 30 },
  { label: "Quarterly", days: 90 },
];

// One-line status under the cadence chips: when you last reached out + whether
// a check-in is due. Reflects journal mentions and manual catch-ups together.
function peopleContactLine(p) {
  const bits = [];
  if (p.last_contact) bits.push(`Last reached out ${fmtNoteDate(p.last_contact)}`);
  else if (p.days_since_last_seen != null) bits.push(`Last wrote about them ${p.days_since_last_seen}d ago`);
  if (p.cadence_days) {
    bits.push(p.overdue ? `<b style="color:var(--danger);">check-in overdue</b>` : `on track`);
  }
  return bits.join(" · ");
}

function closePersonModal() { $("person-modal").classList.remove("active"); }

async function openPersonModal(key) {
  const back = $("person-modal");
  const host = $("person-modal-inner");
  back.classList.add("active");
  host.innerHTML = `<div class="empty"><h3>Loading…</h3></div>`;
  let p;
  try { p = await api(`/people/${encodeURIComponent(key)}`); }
  catch (e) { host.innerHTML = `<div class="empty"><h3>Couldn't load</h3><p>${escapeHtml(e.message)}</p></div>`; return; }

  const emoColor = `var(--e-${p.top_emotion || "neutral"})`;
  const relOpts = RELATIONSHIP_OPTIONS.map(o =>
    `<option value="${o}"${(p.relationship || "") === o ? " selected" : ""}>${o ? o[0].toUpperCase() + o.slice(1) : "—"}</option>`).join("");
  const notes = (p.notes || []).slice().reverse();
  const notesHtml = notes.length
    ? notes.map(n => `
        <div class="pm-note-row" data-note="${n.id}">
          <div class="pm-note-body">
            <div class="pm-note-text">${escapeHtml(n.text)}</div>
            <div class="pm-note-date">${fmtNoteDate(n.created_at)}</div>
          </div>
          <button class="pm-note-del" data-del="${n.id}" title="Delete note">×</button>
        </div>`).join("")
    : `<div class="pm-note-empty">No notes yet — jot down context, things to remember, follow-ups.</div>`;

  const entryPills = (p.entries || []).slice(0, 12).map(e => `
    <span class="cite-pill" data-id="${e.id}" title="${escapeHtml(e.title || "")}">
      <span class="dot" style="background:var(--e-${e.emotion || "neutral"});"></span>${escapeHtml(e.date)}
    </span>`).join("");

  host.innerHTML = `
    <div class="modal-head">
      <div style="display:flex;gap:14px;align-items:center;">
        <div class="person-avatar" style="background:linear-gradient(135deg, ${emoColor}, ${emoColor});">
          ${escapeHtml((p.name || "?").charAt(0).toUpperCase())}
        </div>
        <div>
          <h2 style="margin:0;">${escapeHtml(p.name)}</h2>
          <div class="meta">
            ${p.mentions ? `${p.mentions} ${p.mentions === 1 ? "mention" : "mentions"}` : "no mentions yet"}
            ${p.avg_intensity != null ? ` · avg ${p.avg_intensity}/10` : ""}
            ${p.days_since_last_seen != null ? ` · last ${p.days_since_last_seen}d ago` : ""}
          </div>
          ${peopleChips(p) ? `<div class="person-chips" style="margin-top:8px;">${peopleChips(p)}</div>` : ""}
        </div>
      </div>
      <button class="btn btn-ghost" id="person-modal-close" aria-label="close">✕</button>
    </div>

    <div class="section-label">Relationship</div>
    <div class="pm-grid">
      <div class="pm-field">
        <label>Type</label>
        <select class="select" id="pm-relationship">${relOpts}</select>
      </div>
      <div class="pm-field">
        <label>Display name</label>
        <input class="input" id="pm-name" value="${escapeHtml(p.name || "")}" maxlength="40">
      </div>
      <div class="pm-field">
        <label>Birthday (YYYY-MM-DD or MM-DD)</label>
        <input class="input" id="pm-birthday" value="${escapeHtml(p.birthday || "")}" placeholder="03-12">
      </div>
    </div>

    <div class="pm-field" style="margin-top:12px;">
      <label>How often do you want to check in?</label>
      <div class="cadence-chips" id="pm-cadence">
        ${CADENCE_PRESETS.map(c => `<button type="button" class="cadence-chip${(p.cadence_days ?? null) === c.days ? " active" : ""}" data-days="${c.days == null ? "" : c.days}">${c.label}</button>`).join("")}
      </div>
      <div class="pm-contact-line" id="pm-contact-line">${peopleContactLine(p)}</div>
    </div>

    <div class="section-label">Notes</div>
    <div id="pm-notes">${notesHtml}</div>
    <div class="pm-add-row">
      <input class="input" id="pm-note-input" placeholder="Add a note…" maxlength="2000">
      <button class="btn" id="pm-note-add">Add</button>
    </div>

    ${entryPills ? `<div class="section-label">Appears in</div><div class="person-entries" style="border:0;padding:0;">${entryPills}</div>` : ""}

    <div class="modal-actions">
      <button class="btn btn-ghost" id="pm-pin">${p.pinned ? "Unpin" : "Pin"}</button>
      <button class="btn btn-ghost" id="pm-hide">${p.hidden ? "Unhide" : "Hide"}</button>
      <button class="btn" id="pm-checkin">I reached out</button>
      <button class="btn btn-primary" id="pm-save">Save</button>
    </div>`;

  // --- wire controls ---
  $("person-modal-close").addEventListener("click", closePersonModal);

  const savePerson = async (extra = {}) => {
    const activeChip = host.querySelector(".cadence-chip.active");
    const cadence = activeChip && activeChip.dataset.days ? parseInt(activeChip.dataset.days, 10) : null;
    const body = {
      relationship: $("pm-relationship").value || null,
      name: $("pm-name").value.trim() || null,
      birthday: $("pm-birthday").value.trim() || null,
      cadence_days: cadence,
      ...extra,
    };
    try {
      await api(`/people/${encodeURIComponent(p.key)}`, { method: "PUT", body: JSON.stringify(body) });
      toast("Saved");
      await openPersonModal(p.key);   // refresh drawer
      loadPeople();                    // refresh grid behind it
    } catch (e) { toast(e.message || "Couldn't save", "error"); }
  };

  // Cadence chips: single-select (clicking one activates it, clears siblings).
  host.querySelectorAll(".cadence-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      host.querySelectorAll(".cadence-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
    });
  });

  $("pm-save").addEventListener("click", () => savePerson());
  $("pm-pin").addEventListener("click", () => savePerson({ pinned: !p.pinned }));
  $("pm-hide").addEventListener("click", () => savePerson({ hidden: !p.hidden }));
  $("pm-checkin").addEventListener("click", async () => {
    try {
      await api(`/people/${encodeURIComponent(p.key)}/checkin`, { method: "POST" });
      toast("Nice — marked as caught up");
      await openPersonModal(p.key);
      loadPeople();
    } catch (e) { toast(e.message || "Couldn't log catch-up", "error"); }
  });

  const addNote = async () => {
    const text = $("pm-note-input").value.trim();
    if (!text) return;
    try {
      await api(`/people/${encodeURIComponent(p.key)}/notes`, { method: "POST", body: JSON.stringify({ text }) });
      await openPersonModal(p.key);
    } catch (e) { toast(e.message || "Couldn't add note", "error"); }
  };
  $("pm-note-add").addEventListener("click", addNote);
  $("pm-note-input").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addNote(); } });

  host.querySelectorAll(".pm-note-del[data-del]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const nid = btn.getAttribute("data-del");
      try {
        await api(`/people/${encodeURIComponent(p.key)}/notes/${nid}`, { method: "DELETE" });
        await openPersonModal(p.key);
      } catch (e) { toast(e.message || "Couldn't delete", "error"); }
    });
  });

  host.querySelectorAll(".cite-pill[data-id]").forEach(el => {
    el.addEventListener("click", async () => {
      const id = el.getAttribute("data-id");
      try { const e = await api(`/journal/${id}`); closePersonModal(); openEntry(e); } catch {}
    });
  });
}

function fmtNoteDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }); }
  catch { return iso.slice(0, 10); }
}

// =========================================================================
// MUSIC (SPOTIFY)
// =========================================================================
async function loadMusic() {
  const host = $("music-content");
  host.innerHTML = `<div class="empty"><h3>Loading…</h3></div>`;
  try {
    const s = await api("/spotify/status");
    if (s.demo) {
      host.innerHTML = `<section class="paper-surface demo-off"><span class="eyebrow">MUSIC &amp; MOOD</span><h3>This one needs your own Spotify.</h3><p>Music &amp; mood reads your personal listening history, so it is switched off in this public demo. Run Innerbloom on your own computer to connect your account.</p></section>`;
      $("spotify-nav-dot").style.display = "none";
      return;
    }
    if (!s.connected) {
      host.innerHTML = `
        <section class="spotify-intro">
          <div class="record-room" aria-hidden="true"><div class="record-disc"><div class="record-label"><small>YOUR DAILY</small><span>soundtrack</span><i></i></div></div><div class="record-caption"><span>SIDE A / THE EVERYDAY</span><span>33⅓ RPM</span></div></div>
          <div class="music-invitation"><div class="music-service"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.42 1.56-.299.421-1.02.599-1.559.3z"/></svg><span>Spotify × Innerbloom</span></div><h3>Some days have<br>a soundtrack.</h3><p>Bring the songs you return to alongside the moments you write about.</p>
          ${s.has_client_id?'<button class="btn btn-primary" id="btn-spotify-login">Connect your Spotify <span class="button-arrow">↗</span></button>':'<button class="btn btn-primary" id="music-setup">Set up Spotify <span class="button-arrow">↗</span></button>'}
          <p class="connection-status">${s.has_client_id?'App configured · ready to connect':'One-time setup · your account stays yours'}</p><button class="text-action" id="music-settings">Connection settings ↗</button></div>
        </section>
        <section class="music-notes"><div><small>01 / LISTEN</small><h4>Your recent rotation</h4><p>Return to the tracks and artists that have been keeping you company.</p></div><div><small>02 / NOTICE</small><h4>Patterns, over time</h4><p>Explore listening habits beside your journal, without treating music as a diagnosis.</p></div><div><small>03 / YOUR CHOICE</small><h4>A connection you control</h4><p>Spotify needs the internet. Your journal stays here. Disconnect whenever you like.</p></div></section>
      `;
      $("music-setup")?.addEventListener("click",()=>switchView('settings'));
      $("music-settings").addEventListener("click",()=>switchView('settings'));
      $("btn-spotify-login")?.addEventListener("click", startSpotifyAuth);
      $("spotify-nav-dot").style.display = "none";
      return;
    }

    // Connected — render hero, mood chart, recent tracks
    $("spotify-nav-dot").style.display = "inline-block";
    host.innerHTML = `
      <section class="music-hero listening-cover"><div><span class="eyebrow">YOUR PERSONAL ROTATION</span><h2>A few songs.<br>A little of you.</h2><div class="connected-person">${s.user?.image?`<img src="${escapeHtml(s.user.image)}" alt=""/>`:''}<span>${escapeHtml(s.user?.display_name||'Your account')}<small>Connected to Spotify</small></span></div></div><div class="cover-record" aria-hidden="true"><div class="record-disc"><div class="record-label"><small>INNERBLOOM</small><span>side A</span><i></i></div></div></div><button class="text-action" id="btn-spotify-disconnect">Disconnect ↗</button></section>
      <section class="music-shelf paper-surface"><div class="section-title"><div><span class="eyebrow">THE RECENT ROTATION</span><h3>Keeping you company.</h3></div><span class="sub">Your latest listens</span></div><div class="track-grid" id="recent-tracks"><p class="muted">Loading your tracks…</p></div></section>
      <section class="music-shelf paper-surface"><div class="section-title"><div><span class="eyebrow">ON REPEAT</span><h3>The ones you return to.</h3></div><select aria-label="Top tracks period" class="select" id="top-range"><option value="short_term">Last 4 weeks</option><option value="medium_term" selected>Last 6 months</option><option value="long_term">All time</option></select></div><div class="track-grid" id="top-tracks"><p class="muted">Finding your favourites…</p></div></section>
      <details class="music-shelf paper-surface genre-details"><summary>The character of your listening <span>Explore genre-based estimates ↗</span></summary><div id="mood-quadrant"><p class="muted">Loading…</p></div></details>
      <section class="music-shelf paper-surface music-reflection"><div class="section-title"><div><span class="eyebrow">A MOMENT TO REFLECT</span><h3>What do you notice?</h3></div><button class="btn btn-primary" id="btn-music-insight">Reflect with me ↗</button></div><div id="music-insight">Explore these patterns alongside your recent writing, with help from your local model.</div></section>
    `;

    $("btn-spotify-disconnect").addEventListener("click", disconnectSpotify);
    $("btn-music-insight").addEventListener("click", runMusicInsight);
    $("top-range").addEventListener("change", loadTopTracks);

    loadMoodQuadrant();
    loadRecentTracks();
    loadTopTracks();
  } catch (e) {
    host.innerHTML = `<div class="empty"><h3>Couldn't load</h3><p>${escapeHtml(e.message)}</p></div>`;
  }
}

// Genre-derived mood scatter — works on every Spotify app (no /audio-features).
// Each track is placed on a 2-D plane (valence × energy) using a curated
// genre→mood map. We also draw a centroid + quadrant histogram so the user
// gets a one-glance read of "what mood is your music in lately".

const QUADRANT_COLORS = {
  "Happy & energetic":     "#22c55e",
  "Calm & content":        "#06b6d4",
  "Tense & intense":       "#ef4444",
  "Mellow & melancholic":  "#8b5cf6",
};

async function loadMoodQuadrant() {
  const host = $("mood-quadrant");
  try {
    const data = await api("/spotify/genre-mood");
    renderMoodQuadrant(data);
  } catch (err) {
    host.innerHTML = `<div style="color:var(--danger);font-size:13px;padding:8px;">Couldn't load genre-mood data. ${escapeHtml(err?.message || "")}</div>`;
  }
}

function renderMoodQuadrant(data) {
  const host = $("mood-quadrant");
  const tracks = (data.tracks || []).filter(t => t.valence != null && t.energy != null);

  if (!tracks.length) {
    host.innerHTML = `
      <div style="color:var(--text-muted);font-size:13px;padding:8px;">
        No genre-based profile is available for these recent tracks. Your listening history is still available above.
      </div>`;
    return;
  }

  const enriched = data.enriched_share || 0;
  const lowCoverage = enriched < 0.4;

  const quadrants = data.quadrants || [];
  const centroid = data.centroid;

  host.innerHTML = `
    ${lowCoverage ? `
      <div style="background:rgba(217,119,6,0.07);border:1px solid rgba(217,119,6,0.22);border-radius:8px;padding:10px 12px;margin-bottom:16px;font-size:12.5px;color:var(--text);line-height:1.55;">
        Only ${Math.round(enriched*100)}% of your recent tracks had genres we recognise — the picture sharpens as you play more.
      </div>` : ""}
    <div class="mood-quadrant-grid">
      <div>
        <div class="quadrant-canvas-wrap" id="mood-scatter-wrap">
          <canvas id="mood-scatter-canvas" style="width:100%;height:100%;display:block;border-radius:10px;"></canvas>
        </div>
        <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:11.5px;color:var(--text-muted);">
          <span><b>Valence →</b> 0 = sad, 1 = happy</span>
          <span><b>Energy ↑</b> 0 = mellow, 1 = intense</span>
          <span>${tracks.length} tracks plotted</span>
        </div>
      </div>
      <div class="quadrant-summary">
        ${centroid ? `
          <div class="quadrant-centroid">
            <div class="quadrant-centroid-label">Your music mood</div>
            <div class="quadrant-centroid-value">${escapeHtml(centroid.label)}</div>
            <div class="quadrant-centroid-sub">valence ${centroid.valence} · energy ${centroid.energy}</div>
          </div>` : ""}
        <div class="quadrant-mix">
          ${quadrants.map(q => {
            const color = QUADRANT_COLORS[q.label] || "#94a3b8";
            const pct = Math.round((q.share || 0) * 100);
            return `
              <div class="quadrant-mix-row" title="${q.count} of ${tracks.length} tracks">
                <span class="swatch" style="background:${color};"></span>
                <div>
                  <div class="label">${escapeHtml(q.label)}</div>
                  <div class="bar-wrap"><div class="bar-fill" style="width:${pct}%;background:${color};"></div></div>
                </div>
                <span class="pct">${pct}%</span>
              </div>`;
          }).join("")}
        </div>
      </div>
    </div>
  `;

  requestAnimationFrame(() => drawMoodScatter(tracks));
}

function drawMoodScatter(tracks) {
  const canvas = $("mood-scatter-canvas");
  const wrap = $("mood-scatter-wrap");
  if (!canvas || !wrap) return;
  const dpr = window.devicePixelRatio || 1;
  const w = wrap.clientWidth, h = wrap.clientWidth;  // square
  canvas.width = w * dpr; canvas.height = h * dpr;
  canvas.style.height = h + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const PAD = { top: 20, right: 18, bottom: 30, left: 36 };
  const cW = w - PAD.left - PAD.right, cH = h - PAD.top - PAD.bottom;

  // Quadrant fills (Russell circumplex tinting)
  const fills = [
    { x0: 0.5, y0: 0,   x1: 1,   y1: 0.5, c: "rgba(34,197,94,0.07)" },  // top-right: happy+energetic
    { x0: 0,   y0: 0,   x1: 0.5, y1: 0.5, c: "rgba(239,68,68,0.06)" },  // top-left: tense+intense
    { x0: 0.5, y0: 0.5, x1: 1,   y1: 1,   c: "rgba(6,182,212,0.06)" },  // bottom-right: calm+content
    { x0: 0,   y0: 0.5, x1: 0.5, y1: 1,   c: "rgba(139,92,246,0.07)" }, // bottom-left: mellow+melancholic
  ];
  for (const q of fills) {
    ctx.fillStyle = q.c;
    ctx.fillRect(PAD.left + q.x0 * cW, PAD.top + q.y0 * cH, (q.x1 - q.x0) * cW, (q.y1 - q.y0) * cH);
  }

  // Grid lines (quartiles)
  ctx.strokeStyle = "rgba(15,23,42,0.06)"; ctx.lineWidth = 1;
  for (let v = 0; v <= 1.0001; v += 0.25) {
    const x = PAD.left + v * cW;
    const y = PAD.top + v * cH;
    ctx.beginPath(); ctx.moveTo(x, PAD.top); ctx.lineTo(x, PAD.top + cH); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(PAD.left + cW, y); ctx.stroke();
  }

  // Midline crosshair (the actual quadrant boundary)
  ctx.strokeStyle = "rgba(15,23,42,0.18)"; ctx.lineWidth = 1.4; ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(PAD.left + cW / 2, PAD.top); ctx.lineTo(PAD.left + cW / 2, PAD.top + cH); ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(PAD.left, PAD.top + cH / 2); ctx.lineTo(PAD.left + cW, PAD.top + cH / 2); ctx.stroke();
  ctx.setLineDash([]);

  // Quadrant labels (faint, top-corners)
  ctx.font = "600 10px 'Urbanist', sans-serif";
  ctx.fillStyle = "rgba(15,23,42,0.32)";
  ctx.textAlign = "left";  ctx.fillText("Tense / intense", PAD.left + 8, PAD.top + 14);
  ctx.textAlign = "right"; ctx.fillText("Happy / energetic", PAD.left + cW - 8, PAD.top + 14);
  ctx.textAlign = "left";  ctx.fillText("Mellow / melancholic", PAD.left + 8, PAD.top + cH - 6);
  ctx.textAlign = "right"; ctx.fillText("Calm / content", PAD.left + cW - 8, PAD.top + cH - 6);

  // Axis ticks
  ctx.font = "10px 'Urbanist', sans-serif";
  ctx.fillStyle = "rgba(100,116,139,0.85)";
  for (const v of [0, 0.5, 1]) {
    ctx.textAlign = "center"; ctx.fillText(v.toFixed(1), PAD.left + v * cW, PAD.top + cH + 14);
    ctx.textAlign = "right";  ctx.fillText((1 - v).toFixed(1), PAD.left - 5, PAD.top + v * cH + 3);
  }
  ctx.fillStyle = "rgba(15,23,42,0.5)";
  ctx.textAlign = "center"; ctx.fillText("valence (positivity)", PAD.left + cW / 2, h - 6);
  ctx.save();
  ctx.translate(12, PAD.top + cH / 2); ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center"; ctx.fillText("energy", 0, 0);
  ctx.restore();

  // Helper: snap track to canvas coords (energy 1 = top)
  const toXY = (t) => [PAD.left + t.valence * cW, PAD.top + (1 - t.energy) * cH];

  // Cluster tracks by (rounded-down to 0.05) so overlapping plays size up
  const buckets = new Map();
  for (const t of tracks) {
    const kx = Math.round(t.valence * 20), ky = Math.round(t.energy * 20);
    const key = `${kx}:${ky}`;
    if (!buckets.has(key)) buckets.set(key, { tracks: [], v: 0, e: 0 });
    const b = buckets.get(key);
    b.tracks.push(t); b.v += t.valence; b.e += t.energy;
  }

  // Dot pass — colour by quadrant
  for (const b of buckets.values()) {
    const v = b.v / b.tracks.length, e = b.e / b.tracks.length;
    const [x, y] = toXY({ valence: v, energy: e });
    const r = 4 + Math.min(10, Math.sqrt(b.tracks.length) * 2.5);
    const q = b.tracks[0].quadrant;
    const color = QUADRANT_COLORS[q] || "#94a3b8";
    // halo
    ctx.beginPath(); ctx.arc(x, y, r + 2, 0, Math.PI * 2);
    ctx.fillStyle = color + "33"; ctx.fill();
    // body
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = color; ctx.globalAlpha = 0.9; ctx.fill();
    ctx.globalAlpha = 1; ctx.strokeStyle = "white"; ctx.lineWidth = 1.5; ctx.stroke();
  }

  // Hover tooltip
  let tip = wrap.querySelector(".scatter-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "scatter-tip";
    tip.style.cssText = "position:absolute;pointer-events:none;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:8px 11px;font-size:11.5px;color:#18181b;white-space:nowrap;opacity:0;transition:opacity 0.12s;z-index:5;box-shadow:0 4px 12px rgba(0,0,0,0.08);max-width:260px;white-space:normal;";
    wrap.appendChild(tip);
  }
  canvas.onmousemove = (ev) => {
    const rect = canvas.getBoundingClientRect();
    const mx = (ev.clientX - rect.left), my = (ev.clientY - rect.top);
    let best = null, bestD = 18;
    for (const b of buckets.values()) {
      const v = b.v / b.tracks.length, e = b.e / b.tracks.length;
      const [x, y] = toXY({ valence: v, energy: e });
      const d = Math.hypot(mx - x, my - y);
      if (d < bestD) { bestD = d; best = b; }
    }
    if (!best) { tip.style.opacity = "0"; return; }
    const names = best.tracks.slice(0, 3).map(t => `<div>· ${escapeHtml(t.name)} <span style="color:#94a3b8;">— ${escapeHtml(t.artist)}</span></div>`).join("");
    const more = best.tracks.length > 3 ? `<div style="color:#94a3b8;margin-top:3px;">+ ${best.tracks.length - 3} more</div>` : "";
    tip.innerHTML = `<div style="font-weight:600;color:${QUADRANT_COLORS[best.tracks[0].quadrant] || "#475569"};margin-bottom:3px;">${escapeHtml(best.tracks[0].quadrant || "—")}</div>${names}${more}`;
    tip.style.left = Math.min(rect.width - 180, Math.max(8, mx + 10)) + "px";
    tip.style.top  = Math.max(8, my - 38) + "px";
    tip.style.opacity = "1";
  };
  canvas.onmouseleave = () => { tip.style.opacity = "0"; };
}

async function loadRecentTracks() {
  try {
    const r = await api("/spotify/recent");
    const host = $("recent-tracks");
    if (!r.tracks.length) { host.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Nothing yet.</div>`; return; }
    host.innerHTML = r.tracks.slice(0, 12).map(t => `
      <div class="track">
        ${t.image ? `<img class="art" src="${t.image}" alt="">` : `<div class="art"></div>`}
        <div class="info">
          <div class="name">${escapeHtml(t.name)}</div>
          <div class="artist">${escapeHtml(t.artist)}</div>
        </div>
      </div>
    `).join("");
  } catch { $("recent-tracks").innerHTML = `<div style="color:var(--danger);font-size:13px;">Couldn't load.</div>`; }
}

async function loadTopTracks() {
  const range = $("top-range")?.value || "medium_term";
  try {
    const r = await api(`/spotify/top?kind=tracks&time_range=${range}`);
    const host = $("top-tracks");
    if (!r.tracks?.length) { host.innerHTML = `<div style="color:var(--text-muted);font-size:13px;">Not enough data.</div>`; return; }
    host.innerHTML = r.tracks.slice(0, 12).map(t => `
      <div class="track">
        ${t.image ? `<img class="art" src="${t.image}" alt="">` : `<div class="art"></div>`}
        <div class="info">
          <div class="name">${escapeHtml(t.name)}</div>
          <div class="artist">${escapeHtml(t.artist)}</div>
        </div>
      </div>
    `).join("");
  } catch { $("top-tracks").innerHTML = `<div style="color:var(--danger);font-size:13px;">Couldn't load.</div>`; }
}

async function runMusicInsight() {
  const box = $("music-insight");
  box.classList.add("loading"); box.textContent = "Listening to your patterns…";
  try {
    const r = await api("/spotify/insight");
    box.classList.remove("loading");
    box.innerHTML = mdToHtml(r.insight || "(nothing returned)");
  } catch {
    box.classList.remove("loading");
    box.textContent = "Couldn't reach the model.";
  }
}

async function disconnectSpotify() {
  if (!confirm("Disconnect Spotify?")) return;
  try { await api("/spotify/disconnect", { method: "POST" }); toast("Spotify disconnected"); loadMusic(); }
  catch { toast("Couldn't disconnect.", "error"); }
}

// ---------- Spotify PKCE ----------
function b64url(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
async function sha256(s) { return crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)); }
function randomVerifier() { const arr = new Uint8Array(64); crypto.getRandomValues(arr); return b64url(arr); }

async function startSpotifyAuth() {
  try {
    const s = await api("/spotify/status");
    if (!s.has_client_id) { toast("Add your Spotify Client ID in Settings.", "error"); switchView("settings"); return; }

    const redirect = s.redirect_uri || location.origin + location.pathname;
    if(new URL(redirect).origin!==location.origin){toast("Open Innerbloom at the registered return address to connect Spotify.","error",6000);return;}
    const state=randomVerifier();sessionStorage.setItem("innerbloom.spotify.state",state);
    const verifier = randomVerifier();
    const challenge = b64url(await sha256(verifier));
    sessionStorage.setItem(SPOTIFY_VERIFIER_KEY, verifier);
    sessionStorage.setItem(SPOTIFY_REDIRECT_KEY, redirect);

    const params = new URLSearchParams({
      client_id: s.client_id,
      state,
      response_type: "code",
      redirect_uri: redirect,
      code_challenge_method: "S256",
      code_challenge: challenge,
      scope: s.scopes || "user-read-recently-played user-top-read user-read-email",
    });
    location.href = `https://accounts.spotify.com/authorize?${params.toString()}`;
  } catch (e) {
    toast("Couldn't start Spotify auth: " + e.message, "error");
  }
}

async function handleSpotifyCallback() {
  const url = new URL(location.href);
  const code = url.searchParams.get("code");
  if(url.searchParams.has("error")){toast("Spotify connection was not completed.","error");history.replaceState({},document.title,location.pathname);return;}
  if (!code) return;
  if(!sessionStorage.getItem("innerbloom.spotify.state")||url.searchParams.get("state")!==sessionStorage.getItem("innerbloom.spotify.state")){toast("This Spotify return could not be verified. Please connect again.","error");history.replaceState({},document.title,location.pathname);return;}
  const verifier = sessionStorage.getItem(SPOTIFY_VERIFIER_KEY);
  const redirect = sessionStorage.getItem(SPOTIFY_REDIRECT_KEY) || location.origin + location.pathname;
  if (!verifier) { toast("Missing PKCE verifier.", "error"); return; }

  try {
    await api("/spotify/exchange", {
      method: "POST",
      body: JSON.stringify({ code, code_verifier: verifier, redirect_uri: redirect }),
    });
    sessionStorage.removeItem("innerbloom.spotify.state");
    sessionStorage.removeItem(SPOTIFY_VERIFIER_KEY);
    sessionStorage.removeItem(SPOTIFY_REDIRECT_KEY);
    toast("Spotify connected");
    // Clean URL
    history.replaceState({}, document.title, redirect);
    switchView("music");
  } catch (e) {
    toast("Spotify connection failed: " + e.message, "error");
  }
}

// =========================================================================
// SETTINGS
// =========================================================================
async function renderSettings() {
  const host = $("settings-content");
  let status;
  try { status = await api("/spotify/status"); } catch { status = {}; }

  const defaultRedirect = location.origin + location.pathname;

  host.innerHTML = `
    <div class="settings-section spotify-settings">
      <div class="spotify-setup-header"><h3>Your music, in the picture.</h3><span class="setup-status">${status.connected?'Connected':status.has_client_id?'App configured':'Not connected'}</span></div>
      <p class="spotify-setup-intro">Connect Spotify to explore your listening alongside your writing. Your journal entries stay on this device.</p>
      <details class="spotify-setup-fields" ${status.has_client_id?'':'open'}><summary>App connection details</summary>
      <div class="spotify-help">Use the Client ID and exact return address from your <a href="https://developer.spotify.com/dashboard" target="_blank" rel="noopener">Spotify app dashboard</a>. A client secret is not needed.<div class="code-line">${escapeHtml(status.redirect_uri || defaultRedirect)}</div></div>
      <div class="settings-row">
        <label for="spotify-client-id">Client ID</label>
        <input class="input" id="spotify-client-id" placeholder="abc123…" value="${escapeHtml(status.client_id || "")}" />
      </div>
      <div class="settings-row">
        <label for="spotify-redirect">Return address</label>
        <input class="input" id="spotify-redirect" value="${escapeHtml(status.redirect_uri || defaultRedirect)}" />
      </div>
      </details>
      <div class="settings-row" style="justify-content:flex-end;">
        ${status.connected
          ? `<span class="badge green">● Connected as ${escapeHtml(status.user?.display_name || status.user?.id || "user")}</span>
             <button class="btn btn-danger" id="btn-settings-disconnect">Disconnect</button>`
          : `<button class="btn" id="btn-settings-save">Save</button>
             <button class="btn btn-spotify" id="btn-settings-connect">Connect Spotify</button>`}
      </div>
    </div>

    <div class="settings-section">
      <h3>Notifications</h3>
      <div class="desc">
        Innerbloom can nudge you locally — no server, no network. Notifications fire while this tab is open in the background. To get them when the tab is closed, "install" the app from your browser's address bar (Chrome / Edge / Safari support PWA install).
      </div>
      <div id="notif-permission-row" style="margin:8px 0 12px;"></div>
      <div class="settings-row" style="flex-direction:column;align-items:stretch;gap:10px;">
        <label class="notif-row"><span><b>Morning prompt</b> · 8:30 am · "what do you actually want today?"</span><input type="checkbox" id="notif-morning" /></label>
        <label class="notif-row"><span><b>Evening reflection</b> · 9:00 pm · only fires if you haven't written today</span><input type="checkbox" id="notif-evening" /></label>
        <label class="notif-row"><span><b>Streak risk</b> · 10:30 pm · only if today is empty and your streak is &gt; 3 days</span><input type="checkbox" id="notif-streak" /></label>
        <label class="notif-row"><span><b>Month-ago surfacing</b> · ~9:00 am · one nudge if a real "then-vs-now" landed today</span><input type="checkbox" id="notif-anniv" /></label>
        <label class="notif-row"><span><b>Wellbeing alert</b> · when burnout / spiral level goes above "ok"</span><input type="checkbox" id="notif-wellbeing" /></label>
      </div>
      <div class="settings-row" style="justify-content:flex-end;">
        <button class="btn" id="btn-notif-test">Send a test notification</button>
      </div>
    </div>

    <div class="settings-section">
      <h3>Data</h3>
      <div class="desc">Your entries live locally in <code>data/journal.json</code>, chats in <code>data/chat.json</code>. Nothing ever leaves this machine (except Spotify API calls if you connect).</div>
      <div class="settings-row" style="justify-content:flex-end;">
        <button class="btn" id="btn-settings-export">Export .md</button>
        <button class="btn btn-danger" id="btn-settings-clear-chat">Clear chat history</button>
      </div>
    </div>

    <div class="settings-section">
      <h3>Shortcuts</h3>
      <div class="desc">
        <b>⌘/Ctrl-K</b> — Command palette &nbsp;·&nbsp;
        <b>⌘/Ctrl-S</b> — Save entry &nbsp;·&nbsp;
        <b>W · E · C · I · G</b> — Jump between views (when no element is focused) &nbsp;·&nbsp;
        <b>Esc</b> — Close modal or palette
      </div>
    </div>

    <div class="settings-section">
      <h3>On-device intelligence</h3>
      <div class="desc">Running locally via Ollama. Current model: <code>${escapeHtml(status.model || "qwen2.5:7b")}</code>. Change via <code>INNERBLOOM_MODEL</code> env var.</div>
    </div>
  `;

  window.reflectWorkspace?.settings();

  $("btn-settings-save")?.addEventListener("click", async () => {
    const client_id = $("spotify-client-id").value.trim();
    const redirect_uri = $("spotify-redirect").value.trim();
    if (!client_id) { toast("Client ID required.", "error"); return; }
    try { await api("/spotify/config", { method: "POST", body: JSON.stringify({ client_id, redirect_uri }) }); toast("Saved."); renderSettings(); }
    catch (e) { toast("Save failed: " + e.message, "error"); }
  });

  $("btn-settings-connect")?.addEventListener("click", async () => {
    const client_id = $("spotify-client-id").value.trim();
    const redirect_uri = $("spotify-redirect").value.trim();
    if (!client_id) { toast("Client ID required.", "error"); return; }
    try {
      await api("/spotify/config", { method: "POST", body: JSON.stringify({ client_id, redirect_uri }) });
      await startSpotifyAuth();
    } catch (e) { toast("Save failed: " + e.message, "error"); }
  });

  $("btn-settings-disconnect")?.addEventListener("click", disconnectSpotify);
  $("btn-settings-export")?.addEventListener("click", exportMarkdown);
  $("btn-settings-clear-chat")?.addEventListener("click", async () => {
    if (!confirm("Clear the entire chat history?")) return;
    try { await api("/chat", { method: "DELETE" }); toast("Chat cleared."); }
    catch { toast("Couldn't clear.", "error"); }
  });

  // Bind notification toggles + permission row
  if (typeof Notif !== "undefined") Notif.bindSettings();
}

// =========================================================================
// EXPORT
// =========================================================================
async function exportMarkdown() {
  try {
    const r = await fetch(API + "/export");
    if (!r.ok) throw new Error("Export unavailable");
    const md = await r.text();
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `reflect-journal-${new Date().toISOString().slice(0, 10)}.md`;
    a.click(); URL.revokeObjectURL(url);
    toast("Exported as markdown");
  } catch { toast("Export failed.", "error"); }
}
$("nav-export").addEventListener("click", exportMarkdown);

// =========================================================================
// COMMAND PALETTE
// =========================================================================
let paletteActiveIdx = 0;
let paletteItems = [];

function openPalette() {
  $("palette").classList.add("active");
  $("palette-input").value = "";
  renderPalette("");
  setTimeout(() => $("palette-input").focus(), 20);
}
function closePalette() { $("palette").classList.remove("active"); }

async function renderPalette(q) {
  const list = $("palette-list");
  const actions = [
    { label: "Go to Write",    sub: "W",  fn: () => switchView("write") },
    { label: "Go to Entries",  sub: "E",  fn: () => switchView("entries") },
    { label: "Go to Chat",     sub: "C",  fn: () => switchView("chat") },
    { label: "Go to Insights", sub: "I",  fn: () => switchView("insights") },
    { label: "Go to Memory graph", sub: "G", fn: () => switchView("graph") },
    { label: "Go to People",   sub: "",   fn: () => switchView("people") },
    { label: "Go to Music & Mood", sub: "", fn: () => switchView("music") },
    { label: "Go to Settings", sub: "",   fn: () => switchView("settings") },
    { label: "New prompt",     sub: "",   fn: () => { switchView("write"); loadPrompt(); } },
    { label: "Export markdown", sub: "", fn: () => exportMarkdown() },
    { label: "Analyze all entries", sub: "", fn: () => { switchView("insights"); setTimeout(() => $("btn-analyze").click(), 100); } },
  ];
  const ql = q.trim().toLowerCase();

  let html = "";
  const filteredActions = ql
    ? actions.filter(a => a.label.toLowerCase().includes(ql))
    : actions;

  if (filteredActions.length) {
    html += `<div class="palette-section-label">Actions</div>`;
    html += filteredActions.map((a, i) => `
      <div class="palette-item" data-kind="action" data-idx="${i}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
        <span class="title">${escapeHtml(a.label)}</span>
        ${a.sub ? `<span class="sub kbd-inline">${a.sub}</span>` : ""}
      </div>
    `).join("");
  }

  paletteItems = filteredActions.map(a => ({ kind: "action", fn: a.fn }));

  if (ql) {
    try {
      const r = await api(`/search?q=${encodeURIComponent(q)}`);
      const results = r.results || [];
      if (results.length) {
        html += `<div class="palette-section-label">Entries</div>`;
        results.slice(0, 8).forEach((e, i) => {
          html += `<div class="palette-item" data-kind="entry" data-idx="${paletteItems.length}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/></svg>
            <span class="title">${escapeHtml(e.title || e.summary || "Untitled")}</span>
            <span class="sub">${(e.timestamp || "").slice(0, 10)}</span>
          </div>`;
          paletteItems.push({ kind: "entry", fn: () => openEntry(e) });
        });
      }
    } catch {}
  }

  if (!paletteItems.length) html = `<div style="padding:20px;color:var(--text-muted);font-size:13px;text-align:center;">No matches.</div>`;

  list.innerHTML = html;
  paletteActiveIdx = 0;
  updatePaletteActive();
  list.querySelectorAll(".palette-item").forEach((el, i) => {
    el.addEventListener("click", () => { paletteItems[i]?.fn?.(); closePalette(); });
    el.addEventListener("mouseenter", () => { paletteActiveIdx = i; updatePaletteActive(); });
  });
}
function updatePaletteActive() {
  $$(".palette-item").forEach((el, i) => el.classList.toggle("active", i === paletteActiveIdx));
}

$("btn-palette").addEventListener("click", openPalette);
$("palette-input").addEventListener("input", (e) => renderPalette(e.target.value));
$("palette").addEventListener("click", (e) => { if (e.target.id === "palette") closePalette(); });
$("palette-input").addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closePalette(); }
  else if (e.key === "ArrowDown") { e.preventDefault(); paletteActiveIdx = Math.min(paletteActiveIdx + 1, paletteItems.length - 1); updatePaletteActive(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); paletteActiveIdx = Math.max(paletteActiveIdx - 1, 0); updatePaletteActive(); }
  else if (e.key === "Enter") { e.preventDefault(); paletteItems[paletteActiveIdx]?.fn?.(); closePalette(); }
});

// (Grow section removed — was a separate view; now consolidated into Insights/Chat.)
function todayStr() { return new Date().toISOString().slice(0, 10); }

// All Grow section JS removed.

// =========================================================================
// KEYBOARD SHORTCUTS
// =========================================================================
window.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); openPalette(); return; }
  if ((e.metaKey || e.ctrlKey) && e.key === "s" && $("view-write").classList.contains("active")) {
    e.preventDefault(); saveEntry(); return;
  }
  if (e.key === "Escape") { closeModal(); closePalette(); return; }
});

// =========================================================================
// INIT
// =========================================================================
(async function init() {
  $("greeting").textContent = TITLES.write()[1];
  // Handle Spotify OAuth callback if we've landed here with ?code=
  if (new URL(location.href).searchParams.get("code")) {
    await handleSpotifyCallback();
  } else {
    // Restore last view (fixes redirect-on-reload from Live Server etc.)
    try {
      const last = localStorage.getItem(VIEW_KEY);
      if (last && last !== "write" && $(`view-${last}`)) switchView(last);
    } catch {}
  }
  updateHealth();
  loadPrompt();
  loadAnniversary();
  updateStreak();
  try { const s = await api("/spotify/status"); if (s.connected) $("spotify-nav-dot").style.display = "inline-block"; } catch {}
  setInterval(updateHealth, 30000);
  Notif.start();
  startInsightPolling();
})();

// =========================================================================
// INSIGHT REFRESH PROGRESS
// =========================================================================
// Backend now runs the 4 insight engines in background threads (triggered
// either by /insights/*/refresh or automatically every N entries). We
// poll /insights/status to show a small spinner in the topbar while any
// engine is running, and to auto-refetch the cards once they finish.
let _insightLastFingerprint = "";
let _insightWasRunning = false;
async function _tickInsightStatus() {
  try {
    const s = await api("/insights/status");
    const badge = $("insight-badge");
    const txt = $("insight-badge-text");
    const running = s.running_count || 0;
    const done = s.total - running;
    if (running > 0) {
      badge.style.display = "inline-flex";
      txt.textContent = `insights catching up · ${done}/${s.total}`;
      _insightWasRunning = true;
    } else {
      badge.style.display = "none";
      // If we just transitioned from running → idle, refresh the cards if
      // we're on the Insights view.
      if (_insightWasRunning) {
        _insightWasRunning = false;
        if (document.getElementById("view-insights")?.classList.contains("active")) {
          loadContradictions(); loadTriggers(); loadWellbeing(); loadNarrative();
        }
      }
    }
  } catch { /* ignore — server may just be down */ }
}
function startInsightPolling() {
  _tickInsightStatus();
  setInterval(_tickInsightStatus, 3500);
}

// =========================================================================
// NOTIFICATIONS
// =========================================================================
// Browser Notification API only — no service worker, no remote push. Means:
//   - Fires while the tab is open (foregrounded or backgrounded).
//   - Survives tab restore on Mac/Linux as long as the browser kept the tab.
//   - To fire when the tab is closed, install as a PWA (Chrome/Edge handle
//     installation; the local manifest below makes Innerbloom installable).
//
// Each notification kind has a "fire once per day" guard via localStorage.
// The scheduler ticks every minute and emits whatever's due.
const Notif = (() => {
  const PREFS_KEY  = "innerbloom.notif.prefs";
  const FIRED_KEY  = "innerbloom.notif.fired";

  const DEFAULT_PREFS = {
    morning:    false,
    evening:    false,
    streak:     false,
    anniv:      false,
    wellbeing:  false,
  };

  const SCHEDULE = {
    morning:   { hour: 8,  minute: 30 },
    evening:   { hour: 21, minute: 0  },
    streak:    { hour: 22, minute: 30 },
    anniv:     { hour: 9,  minute: 0  },
    wellbeing: { hour: 19, minute: 0  },
  };

  function loadPrefs() {
    try { return { ...DEFAULT_PREFS, ...(JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")) }; }
    catch { return { ...DEFAULT_PREFS }; }
  }
  function savePrefs(p) { try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch {} }

  function loadFired() {
    try {
      const raw = localStorage.getItem(FIRED_KEY);
      const obj = raw ? JSON.parse(raw) : {};
      const today = new Date().toISOString().slice(0, 10);
      // Reset stale day-keys so each day starts fresh
      if (obj._day !== today) return { _day: today };
      return obj;
    } catch { return { _day: new Date().toISOString().slice(0, 10) }; }
  }
  function markFired(kind) {
    const f = loadFired();
    f[kind] = true;
    try { localStorage.setItem(FIRED_KEY, JSON.stringify(f)); } catch {}
  }
  function alreadyFiredToday(kind) {
    return !!loadFired()[kind];
  }

  function permState() {
    if (!("Notification" in window)) return "unsupported";
    return Notification.permission;  // "default" | "granted" | "denied"
  }

  async function requestPerm() {
    if (!("Notification" in window)) return "unsupported";
    if (Notification.permission === "granted") return "granted";
    try { return await Notification.requestPermission(); }
    catch { return Notification.permission; }
  }

  function fire(kind, title, body, onclick) {
    if (permState() !== "granted") return;
    try {
      const n = new Notification(title, {
        body,
        tag: `innerbloom-${kind}`,
        icon: "data:image/svg+xml;utf8," + encodeURIComponent(
          `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>
             <rect width='32' height='32' rx='8' fill='#4f7c5a'/>
             <path d='M16 25 V17 M16 21 C 19 20, 21 18, 21 15 M16 17 C 11 15, 9 10, 12 6 C 14 8, 16 11, 16 17 Z'
                   stroke='white' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/>
           </svg>`),
        silent: false,
      });
      n.onclick = () => {
        window.focus();
        if (onclick) onclick();
        n.close();
      };
      markFired(kind);
    } catch (e) { /* swallow */ }
  }

  async function hasEntryToday() {
    try {
      const r = await api("/journal?limit=1");
      const e = (r.entries || [])[0];
      if (!e) return false;
      return (e.timestamp || "").slice(0, 10) === new Date().toISOString().slice(0, 10);
    } catch { return false; }
  }

  async function evaluate() {
    const prefs = loadPrefs();
    if (Object.values(prefs).every(v => !v)) return;
    if (permState() !== "granted") return;

    const now = new Date();
    const hm = now.getHours() * 60 + now.getMinutes();
    const dueWindow = 10;  // fire if we're within 10 min after the scheduled time

    const isDue = kind => {
      const t = SCHEDULE[kind];
      const tm = t.hour * 60 + t.minute;
      return hm >= tm && hm <= tm + dueWindow;
    };

    // Morning
    if (prefs.morning && isDue("morning") && !alreadyFiredToday("morning")) {
      let prompt = "What do you actually want today?";
      try { const r = await api("/prompt"); if (r.prompt) prompt = r.prompt; } catch {}
      fire("morning", "Innerbloom — morning", prompt, () => switchView("write"));
    }

    // Evening — only if no entry today
    if (prefs.evening && isDue("evening") && !alreadyFiredToday("evening")) {
      if (!(await hasEntryToday())) {
        fire("evening", "Innerbloom — evening", "Two sentences before bed?",
          () => { switchView("write"); $("entry-text")?.focus(); });
      } else {
        markFired("evening");  // still mark to avoid retry loop
      }
    }

    // Streak risk
    if (prefs.streak && isDue("streak") && !alreadyFiredToday("streak")) {
      try {
        const s = await api("/stats");
        if (s.streak_current > 3 && !(await hasEntryToday())) {
          fire("streak", "Streak at risk", `You're at ${s.streak_current} days. Tap to keep it.`,
            () => { switchView("write"); $("entry-text")?.focus(); });
        } else { markFired("streak"); }
      } catch {}
    }

    // Anniversary surfacing — only if /anniversary returns something today
    if (prefs.anniv && isDue("anniv") && !alreadyFiredToday("anniv")) {
      try {
        const r = await api("/anniversary?days=30&spread=6&with_reflection=false");
        if (r && r.available && r.then && r.then.count) {
          fire("anniv", "A month ago you wrote…",
            `${r.then.count} ${r.then.count === 1 ? "entry" : "entries"} from around then. See what's shifted.`,
            () => { switchView("write"); setTimeout(openAnnivModal, 120); });
        } else { markFired("anniv"); }
      } catch {}
    }

    // Wellbeing alert
    if (prefs.wellbeing && isDue("wellbeing") && !alreadyFiredToday("wellbeing")) {
      try {
        const r = await api("/insights/wellbeing");
        const bl = r?.burnout?.level || "ok";
        const sl = r?.spiral?.level  || "ok";
        const worst = (level => level === "high" ? 3 : level === "elevated" ? 2 : level === "watch" ? 1 : 0);
        const top = Math.max(worst(bl), worst(sl));
        if (top >= 1) {
          const which = worst(bl) >= worst(sl) ? "burnout" : "spiral";
          fire("wellbeing", `Wellbeing — ${which} level: ${which === "burnout" ? bl : sl}`,
            "Worth a moment? Open Insights for the read.",
            () => switchView("insights"));
        } else { markFired("wellbeing"); }
      } catch {}
    }
  }

  function start() {
    // Tick every 60s. evaluate() is cheap & guarded.
    setInterval(evaluate, 60_000);
    // Also run once at startup so a reopen after the scheduled minute still fires.
    setTimeout(evaluate, 4000);
  }

  // --- Settings UI binding (called by renderSettings) ----------------
  function bindSettings() {
    const prefs = loadPrefs();
    ["morning", "evening", "streak", "anniv", "wellbeing"].forEach(k => {
      const el = document.getElementById(`notif-${k}`);
      if (!el) return;
      el.checked = !!prefs[k];
      el.addEventListener("change", async () => {
        if (el.checked && permState() !== "granted") {
          const r = await requestPerm();
          if (r !== "granted") {
            el.checked = false;
            renderPermissionRow();
            return;
          }
        }
        prefs[k] = el.checked;
        savePrefs(prefs);
        renderPermissionRow();
      });
    });

    document.getElementById("btn-notif-test")?.addEventListener("click", async () => {
      const r = await requestPerm();
      if (r !== "granted") {
        toast("Permission denied. Allow notifications in your browser settings.", "error");
        renderPermissionRow();
        return;
      }
      fire("__test", "Innerbloom — test", "If you can read this, notifications work.");
    });

    renderPermissionRow();
  }

  function renderPermissionRow() {
    const host = document.getElementById("notif-permission-row");
    if (!host) return;
    const s = permState();
    const palette = {
      unsupported: { c: "var(--text-muted)", t: "Your browser doesn't support notifications." },
      default:     { c: "var(--warning)",    t: "Permission not yet requested — toggling any option below will ask." },
      granted:     { c: "var(--success)",    t: "Permission granted. You're good." },
      denied:      { c: "var(--danger)",     t: "Permission denied. Reset it in your browser's site settings." },
    }[s];
    host.innerHTML = `<span style="display:inline-flex;align-items:center;gap:8px;font-size:12.5px;color:${palette.c};">
      <span style="width:8px;height:8px;border-radius:50%;background:${palette.c};box-shadow:0 0 0 3px rgba(0,0,0,0.04);"></span>
      ${escapeHtml(palette.t)}
    </span>`;
  }

  return { start, bindSettings, fire };
})();
