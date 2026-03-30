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
 *   real-time logging during the day.
 *
 * CLIENT-ONLY FEATURES (not persisted to the database):
 *   The following data lives only in the browser's in-memory JS state and is
 *   lost on page reload:
 *
 *   1. Track-level notes      — data[trackName] entries with desc "__TRACK_NOTE__".
 *                                Created via the "Add Note" form on each track card.
 *   2. Event sub-notes        — ev.notes[] array on each event entry.
 *                                Created via the "+ Sub-note" button on event items.
 *   3. Inline event edits     — editing time/desc of an event via the popup modal
 *                                only updates the in-memory object, not the DB.
 *   4. Client-added events    — events created via the popup modal (not from the API)
 *                                exist only in `data[trackName]` and have no `eventId`.
 *   5. Client-side deletions  — deleting events, notes, or tracks only removes them
 *                                from in-memory state; DB records are untouched.
 *
 *   Server-persisted features:
 *   - Radio channels (saved via /cal/api/track/<id>/channel/)
 *   - Actual start/end stamps (saved via /cal/api/event/<id>/stamp/)
 *   - Scheduled events loaded from /cal/api/dashboard-events/ (read-only)
 */


// ============================================================
// Configuration
// ============================================================

const CURRENT_USER_NAME = (document.getElementById("currentUserName") || {}).value || "";
const API_URL = "/cal/api/dashboard-events/";


// ============================================================
// In-memory state (no localStorage)
// ============================================================

let data          = {};   // trackName → [events]
let trackChannels = {};   // trackName → channel int
let trackIds      = {};   // trackName → asset pk
let trackColors   = {};
let trackSubtracks = {};  // parentName → { subName: { id, radio_channel, events: [] } }
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
    trackIds      = {};
    trackColors   = {};
    trackSubtracks = {};

    function parseEvents(events, color) {
      const result = [];
      for (const ev of (events || [])) {
        const startHHMM = isoToLocalHHMM(ev.start_time);
        const endHHMM   = isoToLocalHHMM(ev.end_time);
        let timeStr = "";
        if (startHHMM && endHHMM) timeStr = `${startHHMM}-${endHHMM}`;
        else if (startHHMM) timeStr = startHHMM;
        const isImpromptu = !!ev.is_impromptu;
        const notes = [];
        if (ev.description && ev.description.trim()) notes.push(ev.description.trim());
        result.push({
          time: timeStr, scheduledTime: timeStr,
          desc: ev.title || "(untitled)", notes, channel: "",
          eventId: ev.id, isScheduled: true, isImpromptu: isImpromptu,
          actualStart: ev.actual_start || null,
          actualEnd: ev.actual_end || null,
          _trackColor: color || null,
          radioChannelOverride: ev.radio_channel || null,
        });
      }
      return result;
    }

    for (const [trackName, trackInfo] of Object.entries(apiTracks)) {
      if (trackInfo.id) trackIds[trackName] = trackInfo.id;
      if (trackInfo.color) trackColors[trackName] = trackInfo.color;
      if (trackInfo.radio_channel) trackChannels[trackName] = trackInfo.radio_channel;
      data[trackName] = parseEvents(trackInfo.events, trackInfo.color);

      // Parse subtracks
      if (trackInfo.subtracks && typeof trackInfo.subtracks === "object") {
        trackSubtracks[trackName] = {};
        for (const [subName, subInfo] of Object.entries(trackInfo.subtracks)) {
          trackIds[`${trackName}::${subName}`] = subInfo.id;
          if (subInfo.radio_channel) trackChannels[`${trackName}::${subName}`] = subInfo.radio_channel;
          trackSubtracks[trackName][subName] = {
            id: subInfo.id,
            radio_channel: subInfo.radio_channel,
            events: parseEvents(subInfo.events, trackInfo.color),
          };
        }
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


// (Export / Import helpers removed — data is server-managed)


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

const eventPopup        = document.getElementById("eventPopup");
const eventPopupBox     = document.getElementById("eventPopupBox");
const eventModalForm    = document.getElementById("eventModalForm");
const eventModalTrackEl = document.getElementById("eventModalTrackName");
const modalTrackIdInput = document.getElementById("modalTrackId");
const modalTitleInput   = document.getElementById("modalTitle");
const modalDescInput    = document.getElementById("modalDesc");
const modalError        = document.getElementById("modalError");
const modalSubmitBtn    = document.getElementById("eventModalSubmit");
const modalFullFormLink = document.getElementById("modalFullFormLink");

function openEventModal(trackName, trackId, anchorEl) {
  modalTrackName = trackName;
  eventModalTrackEl.textContent = trackName;
  modalTrackIdInput.value = trackId || "";
  modalTitleInput.value = "";
  modalDescInput.value = "";
  modalError.hidden = true;
  modalError.textContent = "";
  modalSubmitBtn.disabled = false;
  modalSubmitBtn.textContent = "Create";

  // Set "Open full form" link
  const dateStr = toISODateStr(currentDate);
  let fullFormUrl = `/cal/event/new/?next=/cal/dashboard/&date=${dateStr}`;
  if (trackId) fullFormUrl += `&track=${trackId}`;
  modalFullFormLink.href = fullFormUrl;

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

  modalTitleInput.focus();
}

function closeEventModal() {
  eventPopup.hidden = true;
  modalTrackName = null;
}

eventPopup.querySelector(".event-popup__close").addEventListener("click", closeEventModal);
document.getElementById("eventModalCancel").addEventListener("click", closeEventModal);
eventPopup.addEventListener("click", (e) => { if (e.target === eventPopup) closeEventModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !eventPopup.hidden) closeEventModal(); });

eventModalForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = modalTitleInput.value.trim();
  if (!title) return;

  const trackId = parseInt(modalTrackIdInput.value, 10);
  if (!trackId) {
    modalError.textContent = "No track selected.";
    modalError.hidden = false;
    return;
  }

  // Loading state
  modalSubmitBtn.disabled = true;
  modalSubmitBtn.textContent = "Creating...";
  modalError.hidden = true;

  try {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    const resp = await fetch("/cal/api/event/create/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({
        title: title,
        description: modalDescInput.value.trim(),
        asset_ids: [trackId],
        is_impromptu: true,
      }),
    });

    if (resp.ok) {
      closeEventModal();
      showStampToast("Impromptu event created");
      await fetchAndLoadData();
      render();
    } else {
      const errData = await resp.json().catch(() => ({}));
      modalError.textContent = errData.error || "Failed to create event.";
      modalError.hidden = false;
      modalSubmitBtn.disabled = false;
      modalSubmitBtn.textContent = "Create";
    }
  } catch (err) {
    modalError.textContent = "Network error — could not reach server.";
    modalError.hidden = false;
    modalSubmitBtn.disabled = false;
    modalSubmitBtn.textContent = "Create";
  }
});


// ============================================================
// Rendering
// ============================================================

/**
 * Render a single event item into the given list element.
 * Shared by parent tracks and subtracks for consistent styling.
 */
function renderEventItem(ev, trackLabel, dataSource, listEl, normalizedFilter) {
  const item = cloneTemplate("eventItemTemplate");
  // Remove redundant time chip — time info is shown in the Scheduled/Actual row
  const timeChip = item.querySelector(".time-chip");
  if (timeChip) timeChip.remove();

  // Per-event radio channel dropdown (scheduled events only)
  if (ev.isScheduled && ev.eventId) {
    const chSelect = document.createElement("select");
    chSelect.className = "event-channel-badge";
    chSelect.title = "Event radio channel";

    // Build options: Track default + Ch 11-16
    const defaultOpt = document.createElement("option");
    defaultOpt.value = "";
    defaultOpt.textContent = "Track Ch";
    chSelect.appendChild(defaultOpt);
    for (let ch = 11; ch <= 16; ch++) {
      const opt = document.createElement("option");
      opt.value = String(ch);
      opt.textContent = `Ch ${ch}`;
      chSelect.appendChild(opt);
    }

    // Set current value
    if (ev.radioChannelOverride) {
      chSelect.value = String(ev.radioChannelOverride);
    } else {
      chSelect.value = "";
    }
    chSelect.setAttribute("data-empty", ev.radioChannelOverride ? "false" : "true");

    chSelect.addEventListener("change", async () => {
      const val = chSelect.value;
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
      const resp = await fetch(`/cal/api/event/${ev.eventId}/channel/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({ channel: val ? parseInt(val, 10) : null }),
      });
      if (resp.ok) {
        const result = await resp.json();
        ev.radioChannelOverride = result.radio_channel || null;
        chSelect.setAttribute("data-empty", ev.radioChannelOverride ? "false" : "true");
      } else {
        showStampToast("Failed to set event radio channel");
        chSelect.value = ev.radioChannelOverride ? String(ev.radioChannelOverride) : "";
      }
    });

    const eventMain = item.querySelector(".event-main");
    eventMain.appendChild(chSelect);
  }

  // Actual-time row (scheduled events only)
  if (ev.isScheduled) {
    const actualRow = document.createElement("div");
    actualRow.className = "actual-time-row";

    const schedLabel = document.createElement("span");
    schedLabel.className   = "time-label time-label--scheduled";
    if (ev.isImpromptu && !ev.scheduledTime) {
      schedLabel.textContent = "Impromptu";
      schedLabel.classList.add("time-label--impromptu");
    } else {
      schedLabel.textContent = `Scheduled: ${formatTimeChip(ev.scheduledTime)}`;
    }
    actualRow.appendChild(schedLabel);

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

    const eventMain = item.querySelector(".event-main");
    eventMain.after(actualRow);
  }

  const textEl  = item.querySelector(".event-text");

  const safe = smartHighlight(ev.desc);
  textEl.innerHTML = normalizedFilter ? highlightTerm(safe, filterText) : safe;

  // Remove action buttons and sub-notes from the card
  const actionsEl = item.querySelector(".event-actions");
  if (actionsEl) actionsEl.remove();
  const subList = item.querySelector(".subnotes-list");
  if (subList) subList.remove();

  // Make entire event card clickable — navigate to edit view
  if (ev.eventId) {
    item.style.cursor = "pointer";
    item.addEventListener("click", (e) => {
      // Don't navigate when clicking stamp buttons or editable times
      if (e.target.closest("button") || e.target.closest(".editable-time") || e.target.closest("select")) return;
      window.location.href = `/cal/event/edit/${ev.eventId}/?next=/cal/dashboard/`;
    });
  }

  listEl.appendChild(item);
}

function render() {
  grid.innerHTML = "";
  const normalizedFilter = filterText.trim().toLowerCase();

  Object.entries(data).forEach(([trackName, entries]) => {
    const card    = cloneTemplate("trackCardTemplate");
    const titleEl = card.querySelector(".track-name");
    titleEl.textContent = trackName;

    // Apply track color via CSS custom property on the card element.
    // Track colors disabled in dashboard tracks view — cards use uniform styling.

    // Radio channel dropdown (track-level, persisted server-side)
    const channelSelect = card.querySelector(".radio-channel-select");
    const chVal = trackChannels[trackName];
    if (chVal) channelSelect.value = String(chVal);
    channelSelect.addEventListener("change", async () => {
      const val = channelSelect.value;
      const trackId = trackIds[trackName];
      if (!trackId) return;
      const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
      const resp = await fetch(`/cal/api/track/${trackId}/channel/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({ channel: val ? parseInt(val, 10) : null }),
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.radio_channel) { trackChannels[trackName] = data.radio_channel; }
        else { delete trackChannels[trackName]; }
      } else {
        showStampToast("Failed to set radio channel");
        channelSelect.value = chVal ? String(chVal) : "";
      }
    });

    // Form and button refs
    const quickAddBtn    = card.querySelector(".add-event-btn");
    const eventsListEl   = card.querySelector(".events-list");
    const notesListEl    = card.querySelector(".notes-list");

    on(quickAddBtn,   "click", (e) => {
      const tid = trackIds[trackName];
      openEventModal(trackName, tid, e.target);
    });

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
      renderEventItem(ev, trackName, data[trackName], eventsListEl, normalizedFilter);
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


    // Filter visibility check
    if (normalizedFilter && !matchesFilter && filteredEvents.length === 0) {
      const noteHit = notes.some(n => (n.time || "").toLowerCase().includes(normalizedFilter));
      if (!noteHit) return;
    }

    // Render subtracks as sections inside the card
    const subsContainer = card.querySelector(".subtracks-container");
    const subs = trackSubtracks[trackName];
    if (subs && Object.keys(subs).length > 0) {
      for (const [subName, subInfo] of Object.entries(subs)) {
        const subSection = cloneTemplate("subtrackSectionTemplate");
        subSection.querySelector(".subtrack-name").textContent = subName;

        // Subtrack radio channel dropdown
        const subChSelect = subSection.querySelector(".radio-channel-select");
        const subChKey = `${trackName}::${subName}`;
        const subChVal = trackChannels[subChKey];
        if (subChVal) subChSelect.value = String(subChVal);
        subChSelect.addEventListener("change", async () => {
          const val = subChSelect.value;
          const subId = trackIds[subChKey];
          if (!subId) return;
          const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
          const resp = await fetch(`/cal/api/track/${subId}/channel/`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify({ channel: val ? parseInt(val, 10) : null }),
          });
          if (resp.ok) {
            const d = await resp.json();
            if (d.radio_channel) trackChannels[subChKey] = d.radio_channel;
            else delete trackChannels[subChKey];
          } else {
            showStampToast("Failed to set radio channel");
            subChSelect.value = subChVal ? String(subChVal) : "";
          }
        });

        // Subtrack "+" button — open impromptu event modal
        const subAddBtn = subSection.querySelector(".subtrack-add-btn");
        if (subAddBtn) {
          const subTrackId = trackIds[subChKey] || subInfo.id;
          subAddBtn.addEventListener("click", (e) => {
            openEventModal(subName, subTrackId, e.target);
          });
        }

        // Subtrack events — same rendering as parent track events
        const subEventsList = subSection.querySelector(".subtrack-events-list");
        const subEvents = sortEvents(subInfo.events || []);
        if (subEvents.length === 0) {
          const li = document.createElement("li");
          li.className = "empty-msg";
          li.textContent = "No events";
          subEventsList.appendChild(li);
        } else {
          const subLabel = `${trackName} \u203a ${subName}`;
          subEvents.forEach(ev => {
            renderEventItem(ev, subLabel, subInfo.events, subEventsList, normalizedFilter);
          });
        }

        subsContainer.appendChild(subSection);
      }
    }

    grid.appendChild(card);
  });

  if (Object.keys(data).length === 0) {
    const empty = document.createElement("div");
    empty.style.color   = "var(--muted)";
    empty.style.padding = "16px";
    empty.textContent   = "No tracks with events for this date.";
    grid.appendChild(empty);
  }
}


// ============================================================
// Global controls
// ============================================================

// (Reload button removed — data auto-loads on page load and date change)


// ============================================================
// Boot — fetch from server, then render
// ============================================================

(async function init() {
  initDateNav();
  updateDateDisplay();
  await fetchAndLoadData();
  render();
})();
