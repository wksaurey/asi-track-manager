/*
 * ASI Control Center — Track & Event Logger (Django-integrated)
 *
 * Purpose:
 *   Logs timed events across multiple tracks (racing circuits, fields, etc.)
 *   during an ASI robot test day. Each track gets its own card showing a
 *   chronological list of events, sub-notes, and free-form notes. Operators
 *   can also assign a radio channel number to each track for easy coordination.
 *
 * Data model:
 *   data[trackName] = [
 *     { time: "9:01",       desc: "Robot entered track", channel: "3", notes: ["AJ assisting"] },
 *     { time: "9:01-11:30", desc: "Lap in progress",     channel: undefined, notes: [] },
 *     { time: "Quick note", desc: "__TRACK_NOTE__",       notes: [] }, // track-level note (no timestamp)
 *   ]
 *
 *   trackChannels[trackName] = "12"  // track-level radio channel (shown in timeline row labels)
 *
 * Data source:
 *   On page load, track and event data is fetched from the Django API at
 *   /cal/api/dashboard-events/ and merged into the local data object.
 *   All edits (add event, add note, delete, etc.) are client-side only for
 *   real-time logging during the day. Use Export JSON to back up.
 */


// ============================================================
// Configuration
// ============================================================

const CURRENT_USER_NAME = (document.getElementById("currentUserName") || {}).value || "";
const API_URL = "/cal/api/dashboard-events/";


// ============================================================
// In-memory state (no localStorage)
// ============================================================

let data          = {};
let trackChannels = {};
let trackColors   = {};
let filterText    = "";
let currentDate   = new Date(); // defaults to today


// ============================================================
// Time parsing and formatting
// ============================================================

function minutesBetween(t1, t2) {
  const parse = (t) => {
    const [h, m] = t.split(":").map(Number);
    return h * 60 + m;
  };
  return parse(t2) - parse(t1);
}

function minutesFromTimeStr(t) {
  if (!t) return Number.MAX_SAFE_INTEGER;
  let start = String(t).split("-")[0].trim();
  let bias = 0;
  if (start.startsWith("<")) { start = start.slice(1); bias = -0.1; }
  if (start.startsWith("~")) { start = start.slice(1); bias = +0.1; }
  const m = start.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return Number.MAX_SAFE_INTEGER;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10) + bias;
}

function sortEvents(events) {
  return [...events].sort(
    (a, b) => minutesFromTimeStr(a.time) - minutesFromTimeStr(b.time)
  );
}

function nowHHMM() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function parseHHMM(str) {
  if (!str) return null;
  const s = String(str).trim().replace(/[~<]/g, "");
  const m = s.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

function durationMinutes(startStr, endStr) {
  const s = parseHHMM(startStr);
  const e = parseHHMM(endStr);
  if (s == null || e == null) return null;
  let diff = e - s;
  if (diff < 0) diff += 24 * 60;
  return diff;
}

function formatDuration(mins) {
  if (mins == null) return "";
  const h = Math.floor(mins / 60), m = mins % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function formatTimeChip(timeStr) {
  if (!timeStr) return "—";
  const [startRaw, endRaw] = String(timeStr).split("-").map(s => (s || "").trim());
  if (!endRaw) return startRaw || "—";
  const mins = durationMinutes(startRaw, endRaw);
  const dur  = formatDuration(mins);
  return dur ? `${startRaw}–${endRaw} • ${dur}` : `${startRaw}–${endRaw}`;
}

/**
 * Convert a bare "HH:MM" string to a UTC ISO string using the dashboard's
 * currently selected date and the browser's local timezone.
 */
function localHHMMtoISO(hhmmStr) {
  const [h, m] = hhmmStr.split(":").map(Number);
  const d = new Date(currentDate);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
}

/**
 * Format a UTC ISO datetime string as "HH:MM" in local time.
 * Returns null if parsing fails.
 */
function isoToLocalHHMM(isoStr) {
  if (!isoStr) return null;
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return null;
    const h = String(d.getHours()).padStart(2, "0");
    const m = String(d.getMinutes()).padStart(2, "0");
    return `${h}:${m}`;
  } catch {
    return null;
  }
}

/**
 * Escape HTML special characters to prevent XSS when using innerHTML.
 */
function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}


// ============================================================
// API: fetch and load track data
// ============================================================

// ============================================================
// Date navigation helpers
// ============================================================

function toISODateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function updateDateDisplay() {
  const displayEl = document.getElementById("dateDisplay");
  const inputEl   = document.getElementById("dateInput");
  const todayBtn  = document.getElementById("dateTodayBtn");

  if (displayEl) {
    displayEl.textContent = currentDate.toLocaleDateString("en-US", {
      weekday: "long", year: "numeric", month: "long", day: "numeric"
    });
  }
  if (inputEl) {
    inputEl.value = toISODateStr(currentDate);
  }

  // Highlight Today button when viewing today
  if (todayBtn) {
    const todayStr = toISODateStr(new Date());
    const curStr   = toISODateStr(currentDate);
    todayBtn.classList.toggle("date-today-btn--active", curStr === todayStr);
  }
}

function changeDate(newDate) {
  currentDate = newDate;
  updateDateDisplay();
  fetchAndLoadData().then(() => render());
}


// ============================================================
// Date nav event listeners (wired after DOM is ready)
// ============================================================

function initDateNav() {
  const prevBtn  = document.getElementById("datePrevBtn");
  const nextBtn  = document.getElementById("dateNextBtn");
  const todayBtn = document.getElementById("dateTodayBtn");
  const inputEl  = document.getElementById("dateInput");

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      const d = new Date(currentDate);
      d.setDate(d.getDate() - 1);
      changeDate(d);
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      const d = new Date(currentDate);
      d.setDate(d.getDate() + 1);
      changeDate(d);
    });
  }

  if (todayBtn) {
    todayBtn.addEventListener("click", () => {
      changeDate(new Date());
    });
  }

  if (inputEl) {
    inputEl.addEventListener("change", () => {
      const parts = inputEl.value.split("-").map(Number);
      if (parts.length === 3 && !parts.some(isNaN)) {
        // Construct date in local time to avoid UTC offset shifting the day
        changeDate(new Date(parts[0], parts[1] - 1, parts[2]));
      }
    });
  }
}


/**
 * Fetch events from the Django API and populate the local data object.
 * Existing client-side additions are replaced entirely on reload.
 */
async function fetchAndLoadData() {
  try {
    const dateStr = toISODateStr(currentDate);
    const resp = await fetch(`${API_URL}?date=${dateStr}`, {
      headers: { "Accept": "application/json" },
    });
    if (!resp.ok) {
      console.error(`Dashboard API returned ${resp.status}`);
      return;
    }
    const json = await resp.json();
    const apiTracks = json.tracks;
    if (!apiTracks || typeof apiTracks !== "object") return;

    // Reset in-memory state
    data = {};
    trackChannels = {};
    trackColors   = {};

    for (const [trackName, trackInfo] of Object.entries(apiTracks)) {
      data[trackName] = [];
      if (trackInfo.color) trackColors[trackName] = trackInfo.color;
      const events = Array.isArray(trackInfo.events) ? trackInfo.events : [];

      for (const ev of events) {
        const startHHMM = isoToLocalHHMM(ev.start_time);
        const endHHMM   = isoToLocalHHMM(ev.end_time);

        let timeStr = "";
        if (startHHMM && endHHMM) {
          timeStr = `${startHHMM}-${endHHMM}`;
        } else if (startHHMM) {
          timeStr = startHHMM;
        }

        const notes = [];
        if (ev.description && ev.description.trim()) {
          notes.push(ev.description.trim());
        }

        data[trackName].push({
          time:          timeStr,
          scheduledTime: timeStr,
          desc:          ev.title || "(untitled)",
          notes,
          channel:       "",
          eventId:       ev.id,
          isScheduled:   true,
          actualStart:   ev.actual_start || null,
          actualEnd:     ev.actual_end   || null,
          _trackColor:   trackInfo.color || null,
        });
      }
    }
  } catch (err) {
    console.error("Failed to load dashboard data from API:", err);
  }
}


// ============================================================
// Stamp API — persist actual start/end times to the server
// ============================================================

const STAMP_API_URL = "/cal/api/event/{id}/stamp/";

// ── Error toast ──────────────────────────────────────────────
function showStampToast(message) {
  const el = document.createElement("div");
  el.className = "stamp-toast";
  el.setAttribute("role", "alert");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => { el.classList.add("fade-out"); }, 4500);
  setTimeout(() => { el.remove(); }, 5000);
}

async function stampActualTime(eventId, action, time) {
  try {
    const url  = STAMP_API_URL.replace("{id}", eventId);
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
    const resp = await fetch(url, {
      method:  "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body:    JSON.stringify(time ? { action, time } : { action }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      const msg = body.error || `Stamp API returned ${resp.status}`;
      console.error(msg);
      showStampToast(msg);
      return null;
    }
    return await resp.json();
  } catch (err) {
    console.error("Stamp API error:", err);
    showStampToast("Network error — could not reach server.");
    return null;
  }
}


// ============================================================
// Export / Import helpers (no localStorage — in-memory only)
// ============================================================

function exportData() {
  const exportObj = { version: 3, tracks: data, trackChannels };
  const blob = new Blob([JSON.stringify(exportObj, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  const dt   = new Date();
  const pad  = n => String(n).padStart(2, "0");
  a.download = `tracks_export_${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}_${pad(dt.getHours())}${pad(dt.getMinutes())}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function importFile(file) {
  if (!file) return;
  try {
    const text     = await file.text();
    const incoming = JSON.parse(text);
    if (incoming && typeof incoming === "object" && !Array.isArray(incoming)) {
      if (incoming.tracks || incoming.trackChannels || incoming.version) {
        data          = incoming.tracks && typeof incoming.tracks === "object" ? incoming.tracks : data;
        trackChannels = incoming.trackChannels && typeof incoming.trackChannels === "object" ? incoming.trackChannels : trackChannels;
      } else {
        data = incoming;
      }
      render();
    } else {
      throw new Error("Bad format");
    }
  } catch {
    alert("Import failed. Ensure this is a valid JSON export from this app.");
  }
}


// ============================================================
// Text search highlighting
// ============================================================

function highlightTerm(text, term) {
  if (!term) return escapeHTML(text);
  const safe = escapeHTML(text);
  const esc = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return safe.replace(new RegExp(`(${esc})`, "ig"), "<span class='highlight'>$1</span>");
}

function smartHighlight(text) {
  return CURRENT_USER_NAME ? highlightTerm(text, CURRENT_USER_NAME) : escapeHTML(text);
}


// ============================================================
// DOM helper
// ============================================================

function cloneTemplate(id) {
  return document.getElementById(id).content.firstElementChild.cloneNode(true);
}

function on(el, evt, fn, opts) {
  if (el) el.addEventListener(evt, fn, opts);
}


// ============================================================
// DOM references
// ============================================================

const grid         = document.getElementById("tracksGrid");
const trackCardTpl = document.getElementById("trackCardTemplate");
const eventItemTpl = document.getElementById("eventItemTemplate");
const noteItemTpl  = document.getElementById("noteItemTemplate");


// ============================================================
// Event popup
// ============================================================

let modalTrackName = null;
let modalEditEntry = null;

const eventPopup        = document.getElementById("eventPopup");
const eventPopupBox     = document.getElementById("eventPopupBox");
const eventModalForm    = document.getElementById("eventModalForm");
const eventModalTitle   = document.getElementById("eventModalTitle");
const eventModalTrackEl = document.getElementById("eventModalTrackName");
const modalTimeInput    = document.getElementById("modalTime");
const modalDescInput    = document.getElementById("modalDesc");

function openEventModal(trackName, entry, anchorEl) {
  modalTrackName = trackName;
  modalEditEntry = entry || null;
  eventModalTitle.textContent   = entry ? "Edit Event" : "Add Event";
  eventModalTrackEl.textContent = trackName;
  modalTimeInput.value = entry ? (entry.time || "") : nowHHMM();
  modalDescInput.value = entry ? (entry.desc || "") : "";

  // Show so the box is measurable
  eventPopup.hidden = false;

  // Position near the triggering track card
  const card   = anchorEl ? anchorEl.closest(".track-card") : null;
  const anchor = (card || anchorEl) ? (card || anchorEl).getBoundingClientRect() : null;
  if (anchor) {
    const gap  = 12;
    const vw   = window.innerWidth;
    const vh   = window.innerHeight;
    const boxW = eventPopupBox.offsetWidth;
    const boxH = eventPopupBox.offsetHeight;

    // Prefer right of card, flip left if it would overflow
    let left = anchor.right + gap;
    if (left + boxW > vw - gap) left = anchor.left - boxW - gap;
    left = Math.max(gap, left);

    // Align top with card top, clamp to stay on screen
    let top = anchor.top;
    top = Math.max(gap, Math.min(top, vh - boxH - gap));

    eventPopupBox.style.top  = top  + "px";
    eventPopupBox.style.left = left + "px";
  }

  modalDescInput.focus();
}

function closeEventModal() {
  eventPopup.hidden = true;
  modalTrackName = null;
  modalEditEntry = null;
}

eventPopup.querySelector(".event-popup__close").addEventListener("click", closeEventModal);
document.getElementById("eventModalCancel").addEventListener("click", closeEventModal);
eventPopup.addEventListener("click", (e) => { if (e.target === eventPopup) closeEventModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !eventPopup.hidden) closeEventModal(); });

eventModalForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const time = modalTimeInput.value.trim();
  const desc = modalDescInput.value.trim();
  if (!time || !desc) return;
  if (modalEditEntry) {
    modalEditEntry.time = time;
    modalEditEntry.desc = desc;
  } else {
    data[modalTrackName].push({ time, desc, notes: [] });
  }
  closeEventModal();
  render();
});


// ============================================================
// Rendering
// ============================================================

function render() {
  grid.innerHTML = "";
  const normalizedFilter = filterText.trim().toLowerCase();

  Object.entries(data).forEach(([trackName, entries]) => {
    const card    = cloneTemplate("trackCardTemplate");
    const titleEl = card.querySelector(".track-name");
    titleEl.textContent = trackName;

    // Apply track color via CSS custom property on the card element.
    // The ::before pseudo-element reads var(--track-color) to show a solid color
    // accent bar; falls back to the default site gradient when no color is set.
    const trackColor = trackColors[trackName];
    if (trackColor) {
      card.style.setProperty('--track-color', trackColor);
    }

    // Channel badge (track-level, top-left of card)
    const channelBadge = card.querySelector(".channel-badge");
    const chVal = trackChannels[trackName];
    channelBadge.textContent   = chVal ? `Ch ${chVal}` : "—";
    channelBadge.dataset.empty = chVal ? "false" : "true";
    channelBadge.addEventListener("click", () => {
      const current = trackChannels[trackName] || "";
      const val     = prompt(`Channel for "${trackName}" (leave blank to clear):`, current);
      if (val === null) return;
      const trimmed = val.trim();
      if (trimmed) { trackChannels[trackName] = trimmed; }
      else         { delete trackChannels[trackName]; }
      render();
    });

    // Form and button refs
    const addNoteToggle  = card.querySelector(".add-note-toggle");
    const delTrackBtn    = card.querySelector(".delete-track");
    const noteForm       = card.querySelector(".note-form");
    const cancelNoteBtn  = card.querySelector(".cancel-note");
    const quickAddBtn    = card.querySelector(".add-event-btn");
    const eventsListEl   = card.querySelector(".events-list");
    const notesListEl    = card.querySelector(".notes-list");

    on(quickAddBtn,   "click", () => openEventModal(trackName, null, quickAddBtn));
    on(addNoteToggle, "click", () => noteForm?.classList.toggle("hidden"));
    on(cancelNoteBtn, "click", () => noteForm?.classList.add("hidden"));

    // Card kebab menu
    const menuWrap = card.querySelector(".menu-wrap");
    const menuBtn  = card.querySelector(".menu-btn");
    on(menuBtn, "click", () => menuWrap?.classList.toggle("open"));

    // Separate events from track-level notes
    const events = sortEvents(
      entries.filter(e => e.desc && e.time !== undefined && e.desc !== "__TRACK_NOTE__")
    );
    const notes = entries.filter(e => e.desc === "__TRACK_NOTE__");

    // Filter logic
    let matchesFilter = !normalizedFilter;
    const filteredEvents = events.filter((e) => {
      if (!normalizedFilter) return true;
      const target = `${e.time} ${e.desc} ${(e.notes || []).join(" ")}`.toLowerCase();
      const ok = target.includes(normalizedFilter);
      if (ok) matchesFilter = true;
      return ok;
    });

    // Render each event
    filteredEvents.forEach((ev) => {
      const item = cloneTemplate("eventItemTemplate");
      item.querySelector(".time-chip").textContent = formatTimeChip(ev.time);

      // Actual-time row (scheduled events only)
      if (ev.isScheduled) {
        const actualRow = document.createElement("div");
        actualRow.className = "actual-time-row";

        // Scheduled label
        const schedLabel = document.createElement("span");
        schedLabel.className   = "time-label time-label--scheduled";
        schedLabel.textContent = `Scheduled: ${formatTimeChip(ev.scheduledTime)}`;
        actualRow.appendChild(schedLabel);

        // Actual label + buttons
        const actualLabel = document.createElement("span");
        actualLabel.className = "time-label time-label--actual";

        if (!ev.actualStart) {
          actualLabel.textContent = "Actual: \u2014";
          const startBtn = document.createElement("button");
          startBtn.className = "btn btn-xxs btn-start";
          startBtn.innerHTML = "&#9654; Start";
          startBtn.addEventListener("click", async () => {
            const result = await stampActualTime(ev.eventId, "start");
            if (result) { ev.actualStart = result.actual_start; render(); }
          });
          actualRow.appendChild(actualLabel);
          actualRow.appendChild(startBtn);
        } else if (!ev.actualEnd) {
          const startHHMM = isoToLocalHHMM(ev.actualStart);
          actualLabel.innerHTML = `Actual: <span class="editable-time" title="Click to edit start time">${startHHMM || "?"}</span> \u2013 ...`;
          actualLabel.classList.add("time-label--active");

          // Clear-start button (undo)
          const clearStartBtn = document.createElement("button");
          clearStartBtn.className = "stamp-clear-btn";
          clearStartBtn.innerHTML = "&times;";
          clearStartBtn.setAttribute("aria-label", "Clear actual start time");
          clearStartBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const result = await stampActualTime(ev.eventId, "clear_start");
            if (result) { ev.actualStart = result.actual_start; ev.actualEnd = result.actual_end; render(); }
          });
          actualLabel.appendChild(clearStartBtn);

          // Make start time editable
          const editableStart = actualLabel.querySelector(".editable-time");
          editableStart.addEventListener("click", async (e) => {
            e.stopPropagation();
            const newTime = prompt("Edit actual start time (HH:MM, 24h):", startHHMM || "");
            if (newTime === null) return;
            const trimmed = newTime.trim();
            if (!trimmed.match(/^\d{1,2}:\d{2}$/)) { alert("Invalid format. Use HH:MM (e.g., 09:15)"); return; }
            const result = await stampActualTime(ev.eventId, "start", localHHMMtoISO(trimmed));
            if (result) { ev.actualStart = result.actual_start; render(); }
          });

          const endBtn = document.createElement("button");
          endBtn.className = "btn btn-xxs btn-end";
          endBtn.innerHTML = "&#9632; End";
          endBtn.addEventListener("click", async () => {
            const result = await stampActualTime(ev.eventId, "end");
            if (result) { ev.actualEnd = result.actual_end; render(); }
          });
          actualRow.appendChild(actualLabel);
          actualRow.appendChild(endBtn);
        } else {
          const startHHMM = isoToLocalHHMM(ev.actualStart);
          const endHHMM = isoToLocalHHMM(ev.actualEnd);
          const dur = durationMinutes(startHHMM, endHHMM);
          const durStr = formatDuration(dur);
          actualLabel.innerHTML = `Actual: <span class="editable-time" data-field="start" title="Click to edit start time">${startHHMM}</span><button class="stamp-clear-btn" data-clear="start" aria-label="Clear actual start time">&times;</button>\u2013<span class="editable-time" data-field="end" title="Click to edit end time">${endHHMM}</span><button class="stamp-clear-btn" data-clear="end" aria-label="Clear actual end time">&times;</button>${durStr ? ` \u2022 ${durStr}` : ""}`;
          actualLabel.classList.add("time-label--complete");

          // Clear buttons (undo)
          actualLabel.querySelectorAll(".stamp-clear-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
              e.stopPropagation();
              const field = btn.dataset.clear;
              const action = field === "start" ? "clear_start" : "clear_end";
              const result = await stampActualTime(ev.eventId, action);
              if (result) {
                ev.actualStart = result.actual_start;
                ev.actualEnd = result.actual_end;
                render();
              }
            });
          });

          // Make both times editable
          actualLabel.querySelectorAll(".editable-time").forEach(span => {
            span.addEventListener("click", async (e) => {
              e.stopPropagation();
              const field = span.dataset.field;
              const currentVal = field === "start" ? startHHMM : endHHMM;
              const newTime = prompt(`Edit actual ${field} time (HH:MM, 24h):`, currentVal || "");
              if (newTime === null) return;
              const trimmed = newTime.trim();
              if (!trimmed.match(/^\d{1,2}:\d{2}$/)) { alert("Invalid format. Use HH:MM (e.g., 09:15)"); return; }
              const result = await stampActualTime(ev.eventId, field, localHHMMtoISO(trimmed));
              if (result) {
                if (field === "start") ev.actualStart = result.actual_start;
                else ev.actualEnd = result.actual_end;
                render();
              }
            });
          });

          actualRow.appendChild(actualLabel);
        }

        // Insert after event-main
        const eventMain = item.querySelector(".event-main");
        eventMain.after(actualRow);
      }

      // Per-event channel badge
      const chBadge = item.querySelector(".event-channel-badge");
      if (chBadge) {
        const evCh = ev.channel || "";
        chBadge.textContent    = evCh || "—";
        chBadge.dataset.empty  = evCh ? "false" : "true";
        chBadge.addEventListener("click", () => {
          const val = prompt(`Channel for this event (leave blank to clear):`, evCh);
          if (val === null) return;
          const trimmed = val.trim();
          ev.channel = trimmed || undefined;
          render();
        });
      }

      const textEl  = item.querySelector(".event-text");
      const subList = item.querySelector(".subnotes-list");

      const safe = smartHighlight(ev.desc);
      textEl.innerHTML = normalizedFilter ? highlightTerm(safe, filterText) : safe;

      // Sub-notes
      (ev.notes || []).forEach((n, nIdx) => {
        const li = document.createElement("li");
        li.className = "subnote-item";

        const textSpan = document.createElement("span");
        textSpan.className = "subnote-text";
        textSpan.innerHTML = normalizedFilter ? highlightTerm(n, filterText) : smartHighlight(n);

        const editBtn = document.createElement("button");
        editBtn.className   = "btn btn-xxs btn-outline subnote-edit";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", () => {
          const newVal = prompt("Edit sub-note:", n);
          if (newVal === null) return;
          const trimmed = newVal.trim();
          if (trimmed) { ev.notes[nIdx] = trimmed; render(); }
        });

        const delBtn = document.createElement("button");
        delBtn.className   = "btn btn-xxs btn-danger subnote-delete";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", () => {
          showConfirmModal("Delete this sub-note?", function() {
            ev.notes.splice(nIdx, 1);
            render();
          });
        });

        li.appendChild(textSpan);
        li.appendChild(editBtn);
        li.appendChild(delBtn);
        subList.appendChild(li);
      });

      // Event action buttons
      item.querySelector(".add-subnote").addEventListener("click", () => {
        const val = prompt("Add sub-note (e.g., 'AJ assisting'):");
        if (val && val.trim()) {
          ev.notes = ev.notes || [];
          ev.notes.push(val.trim());
          render();
        }
      });

      item.querySelector(".edit-event").addEventListener("click", (e) => openEventModal(trackName, ev, e.currentTarget));

      item.querySelector(".delete-event").addEventListener("click", () => {
        showConfirmModal("Delete this event?", function() {
          const idxInData = data[trackName].findIndex(x => x === ev);
          if (idxInData > -1) { data[trackName].splice(idxInData, 1); render(); }
        });
      });

      // End button (only for events with no end time)
      (function attachEndButton() {
        if (String(ev.time || "").includes("-")) return;
        const actionsEl = item.querySelector(".event-actions");
        const endBtn    = document.createElement("button");
        endBtn.className   = "btn btn-xxs";
        endBtn.textContent = "End";
        endBtn.title       = "Stamp the current time as this event's end time";
        endBtn.addEventListener("click", () => {
          if (!ev.time) ev.time = nowHHMM();
          const startPart = String(ev.time).split("-")[0].trim();
          ev.time = `${startPart}-${nowHHMM()}`;
          render();
        });
        actionsEl.insertBefore(endBtn, actionsEl.firstChild);
      })();

      eventsListEl.appendChild(item);
    });

    // Empty state
    if (filteredEvents.length === 0 && !normalizedFilter) {
      const emptyLi = document.createElement("li");
      emptyLi.className   = "event-empty";
      emptyLi.textContent = "No events yet — click + to log one";
      eventsListEl.appendChild(emptyLi);
    }

    // Track-level notes
    const notesSection = card.querySelector(".notes-section");
    if (notes.length === 0) notesSection.style.display = "none";

    notes.forEach((n) => {
      const note   = cloneTemplate("noteItemTemplate");
      const textEl = note.querySelector(".note-text");
      textEl.innerHTML = normalizedFilter
        ? highlightTerm(n.time || "", filterText)
        : smartHighlight(n.time || "");
      note.querySelector(".edit-note").addEventListener("click", () => {
        const newText = prompt("Edit note:", n.time || "");
        if (newText === null) return;
        n.time = newText.trim();
        render();
      });
      note.querySelector(".delete-note").addEventListener("click", () => {
        showConfirmModal("Delete this note?", function() {
          const idxInData = data[trackName].findIndex(x => x === n);
          if (idxInData > -1) { data[trackName].splice(idxInData, 1); render(); }
        });
      });
      notesListEl.appendChild(note);
    });

    // New track-level note form submission
    noteForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const fd   = new FormData(noteForm);
      const note = (fd.get("note") || "").toString().trim();
      if (!note) return;
      data[trackName].push({ time: note, desc: "__TRACK_NOTE__", notes: [] });
      noteForm.reset();
      noteForm.classList.add("hidden");
      render();
    });

    // Delete entire track
    delTrackBtn.addEventListener("click", () => {
      showConfirmModal(`Delete track "${trackName}"? This cannot be undone.`, function() {
        delete data[trackName];
        render();
      });
    });

    // Filter visibility check
    if (normalizedFilter && !matchesFilter && filteredEvents.length === 0) {
      const noteHit = notes.some(n => (n.time || "").toLowerCase().includes(normalizedFilter));
      if (!noteHit) return;
    }

    grid.appendChild(card);
  });

  if (Object.keys(data).length === 0) {
    const empty = document.createElement("div");
    empty.style.color   = "var(--muted)";
    empty.style.padding = "16px";
    empty.textContent   = "No tracks yet. Use 'Add Track' to create one, or click 'Reload from Server'.";
    grid.appendChild(empty);
  }
}


// ============================================================
// Global controls
// ============================================================

document.getElementById("searchInput").addEventListener("input", (e) => {
  filterText = e.target.value;
  render();
});

document.getElementById("addTrackForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const inp  = document.getElementById("newTrackName");
  const name = (inp.value || "").trim();
  if (!name) return;
  if (data[name]) { alert("Track already exists."); return; }
  data[name] = [];
  inp.value = "";
  render();
});

document.getElementById("exportBtn").addEventListener("click", exportData);

document.getElementById("importInput").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  await importFile(file);
  e.target.value = "";
});

// Reload from Server — re-fetches the API for the current date and re-renders
document.getElementById("reloadBtn").addEventListener("click", () => {
  showConfirmModal("Reload all track data from the server? Any unsaved client-side additions will be lost.", {
    onConfirm: async function() { await fetchAndLoadData(); render(); },
    confirmLabel: "Reload",
    confirmClass: "btn-primary",
  });
});


// ============================================================
// Header hamburger menu
// ============================================================

(function initHeaderHamburger() {
  const wrap = document.getElementById("headerHamburger");
  if (!wrap) return;
  const btn  = wrap.querySelector(".hamburger-btn");
  const menu = wrap.querySelector(".hamburger-menu");

  function closeMenu() { wrap.classList.remove("open"); btn.setAttribute("aria-expanded","false"); menu.setAttribute("aria-hidden","true"); }
  function openMenu()  { wrap.classList.add("open");    btn.setAttribute("aria-expanded","true");  menu.setAttribute("aria-hidden","false"); }

  btn.addEventListener("click", (e) => { e.stopPropagation(); wrap.classList.contains("open") ? closeMenu() : openMenu(); });
  document.addEventListener("click",   (e) => { if (!wrap.contains(e.target)) closeMenu(); });
  document.addEventListener("keydown",  (e) => { if (e.key === "Escape") closeMenu(); });
  menu.addEventListener("click", (e) => { if (e.target.closest(".menu-item") || e.target.closest("label.menu-item")) closeMenu(); });
})();


// ============================================================
// VIEW TABS
// ============================================================

(function initViewTabs() {
  const tabs        = document.querySelectorAll(".view-tab");
  const tracksView  = document.getElementById("tracksView");
  const tlView      = document.getElementById("timelineView");
  const tracksCtrls = document.getElementById("tracksControls");
  const tlCtrls     = document.getElementById("timelineControls");

  function switchView(view) {
    tabs.forEach(t => t.classList.toggle("active", t.dataset.view === view));
    const isTl = view === "timeline";
    tracksView.classList.toggle("hidden", isTl);
    tlView.classList.toggle("hidden", !isTl);
    tracksCtrls.classList.toggle("hidden", isTl);
    tlCtrls.classList.toggle("hidden", !isTl);
    if (isTl) renderTimeline();
  }

  tabs.forEach(tab => tab.addEventListener("click", () => switchView(tab.dataset.view)));
})();


// ============================================================
// TIMELINE RENDERER
// ============================================================

function renderTimeline() {
  const container = document.getElementById("timelineContainer");

  // Gather all timestamped events
  const trackNames = Object.keys(data);
  const allEvents  = [];

  for (const trackName of trackNames) {
    for (const ev of (data[trackName] || [])) {
      if (!ev.time || ev.desc === "__TRACK_NOTE__") continue;
      const [startRaw, endRaw] = String(ev.time).split("-").map(s => s.trim());
      const startMins = parseHHMM(startRaw);
      if (startMins == null) continue;

      if (ev.isScheduled && ev.actualStart) {
        // Ghost bar for the scheduled window
        allEvents.push({ trackName, ev, startMins, endMins: endRaw ? parseHHMM(endRaw) : null, barType: "scheduled" });

        // Solid bar for the actual window
        const actStartHHMM = isoToLocalHHMM(ev.actualStart);
        const actEndHHMM   = ev.actualEnd ? isoToLocalHHMM(ev.actualEnd) : null;
        const actStartMins = parseHHMM(actStartHHMM);
        if (actStartMins != null) {
          allEvents.push({ trackName, ev, startMins: actStartMins, endMins: actEndHHMM ? parseHHMM(actEndHHMM) : null, barType: "actual" });
        }
      } else {
        allEvents.push({ trackName, ev, startMins, endMins: endRaw ? parseHHMM(endRaw) : null, barType: "default" });
      }
    }
  }

  if (allEvents.length === 0) {
    container.innerHTML = `<div class="tl-empty">No timed events recorded yet.<br><span>Add events from the Tracks view using the + button.</span></div>`;
    return;
  }

  // Axis range
  const nowMins   = new Date().getHours() * 60 + new Date().getMinutes();
  const allStarts = allEvents.map(e => e.startMins);
  const allEnds   = allEvents.map(e => e.endMins ?? e.startMins + 30);
  const axisStart = Math.floor((Math.min(...allStarts) - 30) / 60) * 60;
  const axisEnd   = Math.ceil((Math.max(...allEnds, nowMins) + 30) / 60) * 60;
  const axisSpan  = axisEnd - axisStart;

  const pct = mins => ((mins - axisStart) / axisSpan) * 100;

  function fmtMins(m) {
    const h = Math.floor(m / 60) % 24, min = m % 60;
    return `${String(h).padStart(2,"0")}:${String(min).padStart(2,"0")}`;
  }

  // Channel color map
  const HUE_SLOTS = [
    { bg: "rgba(96,165,250,0.15)",  border: "#60a5fa", text: "#93c5fd" },
    { bg: "rgba(52,211,153,0.15)",  border: "#34d399", text: "#6ee7b7" },
    { bg: "rgba(251,191,36,0.15)",  border: "#fbbf24", text: "#fcd34d" },
    { bg: "rgba(244,114,182,0.15)", border: "#f472b6", text: "#f9a8d4" },
    { bg: "rgba(167,139,250,0.15)", border: "#a78bfa", text: "#c4b5fd" },
  ];
  const chColorCache = {};
  let   chColorIdx   = 0;
  function colorForChannel(ch) {
    const key = ch || "__none__";
    if (!chColorCache[key]) chColorCache[key] = HUE_SLOTS[chColorIdx++ % HUE_SLOTS.length];
    return chColorCache[key];
  }

  // Lane assignment (overlap stacking)
  function assignLanes(events) {
    const sorted = [...events].sort((a, b) => a.startMins - b.startMins);
    const lanes  = [];
    return sorted.map(ev => {
      const evEnd = ev.endMins ?? (ev.startMins + 30);
      let lane = lanes.findIndex(laneEnd => laneEnd <= ev.startMins);
      if (lane === -1) lane = lanes.length;
      lanes[lane] = evEnd;
      return { ...ev, lane };
    });
  }

  // Build rows
  const BLOCK_H  = 38;
  const LANE_GAP = 5;
  const ROW_PAD  = 10;

  // Lighten a hex color by mixing it toward white — used for block text in dark mode
  // so the text is a bright tint of the track color rather than the raw (often too-dark) hex.
  const isDark = document.documentElement.classList.contains('dark-theme');
  function lightenColor(hex, mix) {
    if (!hex || hex.length < 7) return hex;
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgb(${Math.round(r + (255-r)*mix)},${Math.round(g + (255-g)*mix)},${Math.round(b + (255-b)*mix)})`;
  }

  const tracksWithEvents = trackNames.filter(t => allEvents.some(e => e.trackName === t));

  const hours = [];
  for (let m = axisStart; m <= axisEnd; m += 60) hours.push(m);

  const gridLines   = hours.map(m => `<div class="tl-gridline" style="left:${pct(m)}%"></div>`).join("");
  const nowInRange  = nowMins >= axisStart && nowMins <= axisEnd;
  const nowLineBar  = nowInRange ? `<div class="tl-now-line" style="left:${pct(nowMins)}%"></div>` : "";
  const nowLineHead = nowInRange ? `<div class="tl-now-line" style="left:${pct(nowMins)}%"><div class="tl-now-label">now</div></div>` : "";
  const ticks       = hours.map(m => `<div class="tl-tick" style="left:${pct(m)}%">${fmtMins(m)}</div>`).join("");

  const rows = tracksWithEvents.map(trackName => {
    const eventsForTrack = allEvents.filter(e => e.trackName === trackName);
    const laned      = assignLanes(eventsForTrack);
    const laneCount  = laned.length ? Math.max(...laned.map(e => e.lane)) + 1 : 1;
    const laneH      = BLOCK_H + LANE_GAP;
    const rowH       = laneCount * laneH - LANE_GAP + ROW_PAD * 2;

    const blocks = laned.map(({ ev, startMins, endMins, lane, barType }) => {
      const ch          = ev.channel || "";
      // Use _trackColor embedded on the event at load time (from API response).
      // This avoids a separate trackColors map lookup that can fail if the map
      // is stale or keyed differently.
      const tColor      = ev._trackColor;
      const col         = tColor
        ? {
            bg:   tColor + (isDark ? "40" : "28"),    // slightly more opaque so blocks stand out
            border: tColor,
            text: isDark ? lightenColor(tColor, 0.52) : tColor,  // bright tint in dark mode for contrast
          }
        : colorForChannel(ch);
      const isOpen      = endMins == null;
      const resolvedEnd = endMins ?? Math.min(startMins + 60, axisEnd);
      const left        = pct(startMins);
      const width       = Math.max(pct(resolvedEnd) - left, 0.5);
      const topPx       = ROW_PAD + lane * laneH;
      const chip        = formatTimeChip(ev.time);
      const tipId       = `tl-tip-${trackName.replace(/\W/g,"_")}-${startMins}-${lane}-${barType}`;
      const notesHtml   = ev.notes?.length
        ? `<ul class="tl-tooltip-notes">${ev.notes.map(n => `<li>${n}</li>`).join("")}</ul>`
        : `<p class="tl-tooltip-nonotes">No sub-notes recorded.</p>`;

      const barTypeClass = barType === "scheduled" ? " tl-block--ghost"
                         : barType === "actual"    ? " tl-block--actual"
                         : "";

      // Tooltip label suffix based on bar type
      const barLabel = barType === "scheduled" ? " <em>(Scheduled)</em>"
                     : barType === "actual"    ? " <em>(Actual)</em>"
                     : "";

      // For actual bars, show the actual time range in the chip
      const displayChip = barType === "actual"
        ? (() => {
            const s = isoToLocalHHMM(ev.actualStart);
            const e = ev.actualEnd ? isoToLocalHHMM(ev.actualEnd) : null;
            return e ? formatTimeChip(`${s}-${e}`) : `${s} – ...`;
          })()
        : chip;

      return `
        <div class="tl-block${isOpen ? " tl-block--open" : ""}${barTypeClass}"
          style="left:${left}%;width:${width}%;top:${topPx}px;height:${BLOCK_H}px;background:${col.bg};border-color:${col.border}"
          data-tooltip="${tipId}">
          <span class="tl-block-desc" style="color:${col.text}">${ev.desc}</span>
          <span class="tl-block-meta" style="color:${col.text};opacity:.7">${displayChip}${ch ? ` · ${ch}` : ""}</span>
        </div>
        <div class="tl-tooltip hidden" id="${tipId}">
          <div class="tl-tooltip-header">
            <span class="tl-tooltip-desc">${ev.desc}</span>
            ${ch ? `<span class="tl-tooltip-ch">${ch}</span>` : ""}
          </div>
          <div class="tl-tooltip-time">${displayChip}${isOpen ? ' <em>(still active)</em>' : ""}${barLabel}</div>
          <div class="tl-tooltip-track">${trackName}</div>
          ${notesHtml}
        </div>`;
    }).join("");

    const chVal = trackChannels[trackName];
    return `
      <div class="tl-row" style="min-height:${rowH}px">
        <div class="tl-row-label" title="${trackName}">
          <span class="tl-row-name">${trackName}</span>
          ${chVal ? `<span class="tl-row-ch">${chVal}</span>` : ""}
        </div>
        <div class="tl-row-lane" style="height:${rowH}px">
          ${gridLines}${nowLineBar}${blocks}
        </div>
      </div>`;
  }).join("");

  // Legend — only channels actually in use
  const usedChannels = [...new Set(allEvents.map(e => e.ev.channel).filter(Boolean))];
  const legendItems  = usedChannels.map(ch => {
    const col = colorForChannel(ch);
    return `<div class="tl-legend-item">
      <span class="tl-legend-swatch" style="background:${col.bg};border-color:${col.border}"></span>
      <span>${ch}</span>
    </div>`;
  }).join("");

  const hasActual    = allEvents.some(e => e.barType === "actual");
  const hasScheduled = allEvents.some(e => e.barType === "scheduled");
  const barLegend    = [
    hasScheduled ? `<div class="tl-legend-item"><span class="tl-legend-ghost"></span><span>Scheduled</span></div>` : "",
    hasActual    ? `<div class="tl-legend-item"><span class="tl-legend-actual"></span><span>Actual</span></div>`   : "",
  ].join("");

  container.innerHTML = `
    <div class="tl-wrap">
      <div class="tl-header-row">
        <div class="tl-header-label"></div>
        <div class="tl-header-axis">${ticks}${nowLineHead}</div>
      </div>
      <div class="tl-body">${rows}</div>
      <div class="tl-legend">
        ${legendItems}
        ${barLegend}
        ${nowInRange ? `<div class="tl-legend-item"><span class="tl-legend-now"></span><span>Now</span></div>` : ""}
        <div class="tl-legend-item"><span class="tl-legend-open"></span><span>Still active</span></div>
      </div>
    </div>`;

  // Tooltip positioning
  let activeTooltip = null;

  container.querySelectorAll(".tl-block").forEach(block => {
    block.addEventListener("click", e => {
      e.stopPropagation();
      const tip    = document.getElementById(block.dataset.tooltip);
      const isOpen = !tip.classList.contains("hidden");

      if (activeTooltip && activeTooltip !== tip) { activeTooltip.classList.add("hidden"); activeTooltip = null; }
      if (isOpen) { tip.classList.add("hidden"); activeTooltip = null; return; }

      tip.classList.remove("hidden");

      // Tooltip is position:fixed — position directly in viewport coordinates.
      // This avoids scroll-offset math and works regardless of where in the
      // timeline the block sits.
      const blockRect = block.getBoundingClientRect();
      const tipH      = tip.offsetHeight || 160;
      const tipW      = tip.offsetWidth  || 260;
      const margin    = 10;
      const vh        = window.innerHeight;
      const vw        = window.innerWidth;

      // Prefer opening above the block; fall back to below if not enough room.
      const rawTop = (blockRect.top - margin >= tipH + margin)
        ? blockRect.top  - tipH - margin
        : blockRect.bottom + margin;

      tip.style.top    = `${Math.min(Math.max(rawTop, margin), vh - tipH - margin)}px`;
      tip.style.left   = `${Math.min(Math.max(blockRect.left, margin), vw - tipW - margin)}px`;
      tip.style.bottom = "auto";
      tip.style.right  = "auto";
      activeTooltip    = tip;
    });
  });

  const closeTooltip = () => {
    if (activeTooltip) { activeTooltip.classList.add("hidden"); activeTooltip = null; }
  };

  // Close on click anywhere outside a block
  if (renderTimeline._docClickHandler) {
    document.removeEventListener("click", renderTimeline._docClickHandler);
  }
  renderTimeline._docClickHandler = closeTooltip;
  document.addEventListener("click", renderTimeline._docClickHandler);

  // Close on scroll — fixed tooltip stays put while content moves, which is jarring.
  // tl-body scroll: element is fresh each render so no cleanup needed.
  const tlBody = container.querySelector(".tl-body");
  if (tlBody) tlBody.addEventListener("scroll", closeTooltip);

  // Window scroll: clean up previous listener to avoid accumulation.
  if (renderTimeline._scrollHandler) {
    window.removeEventListener("scroll", renderTimeline._scrollHandler, true);
  }
  renderTimeline._scrollHandler = closeTooltip;
  window.addEventListener("scroll", renderTimeline._scrollHandler, true);
}


// ============================================================
// Boot — fetch from server, then render
// ============================================================

(async function init() {
  initDateNav();
  updateDateDisplay();
  await fetchAndLoadData();
  render();
})();
