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
const APP_TZ = window.APP_TZ || "America/Denver";


// ============================================================
// In-memory state (no localStorage)
// ============================================================

let data          = {};   // trackName → [events]
let trackChannels = {};   // trackName → channel int
let trackIds      = {};   // trackName → asset pk
let trackColors   = {};
let trackActive   = {};   // trackName → bool (is_active state)
let trackSubtracks = {};  // parentName → { subName: { id, radio_channel, events: [] } }
let filterText    = "";
let currentDate   = new Date(); // defaults to today
let showUnapproved = true;  // toggle for unapproved event visibility


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
  return new Date().toLocaleTimeString("en-GB", { timeZone: APP_TZ, hour: "2-digit", minute: "2-digit", hour12: false });
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
 * Convert a bare "HH:MM" string (in Eastern Time) to a UTC ISO string
 * using the dashboard's currently selected date.
 */
function localHHMMtoISO(hhmmStr) {
  const [h, m] = hhmmStr.split(":").map(Number);
  const dateStr = toISODateStr(currentDate);
  // Determine the Eastern Time UTC offset for this date
  const probe = new Date(`${dateStr}T12:00:00Z`);
  const utcStr = probe.toLocaleString("en-US", { timeZone: "UTC" });
  const etStr  = probe.toLocaleString("en-US", { timeZone: APP_TZ });
  const offsetMs = new Date(etStr) - new Date(utcStr);
  // Construct the target time as if UTC, then subtract Eastern offset
  const fakeUTC = new Date(`${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00Z`);
  return new Date(fakeUTC.getTime() - offsetMs).toISOString();
}

/**
 * Format an ISO datetime string as "HH:MM" in Eastern Time.
 * Returns null if parsing fails.
 */
function isoToLocalHHMM(isoStr) {
  if (!isoStr) return null;
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleTimeString("en-GB", { timeZone: APP_TZ, hour: "2-digit", minute: "2-digit", hour12: false });
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
  return d.toLocaleDateString("en-CA", { timeZone: APP_TZ });
}

function updateDateDisplay() {
  const displayEl = document.getElementById("dateDisplay");
  const inputEl   = document.getElementById("dateInput");
  const todayBtn  = document.getElementById("dateTodayBtn");

  if (displayEl) {
    displayEl.textContent = currentDate.toLocaleDateString("en-US", {
      weekday: "long", year: "numeric", month: "long", day: "numeric",
      timeZone: APP_TZ
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
    trackActive   = {};
    trackSubtracks = {};

    function parseEvents(events, color) {
      const result = [];
      for (const ev of (events || [])) {
        const startHHMM = isoToLocalHHMM(ev.start_time);
        const endHHMM   = isoToLocalHHMM(ev.end_time);
        let timeStr = "";
        if (startHHMM && endHHMM) timeStr = `${startHHMM}-${endHHMM}`;
        else if (startHHMM) timeStr = startHHMM;
        const notes = [];
        if (ev.description && ev.description.trim()) notes.push(ev.description.trim());
        result.push({
          time: timeStr, scheduledTime: timeStr,
          desc: ev.title || "(untitled)", notes, channel: "",
          eventId: ev.id, isScheduled: true,
          actualStart: ev.actual_start || null,
          actualEnd: ev.actual_end || null,
          _trackColor: color || null,
          radioChannelOverride: ev.radio_channel || null,
          isApproved: ev.is_approved !== false,
          isStopped: !!ev.is_stopped,
          isCurrentlyActive: !!ev.is_currently_active,
          segments: ev.segments || [],
          totalActualSeconds: ev.total_actual_seconds || 0,
        });
      }
      return result;
    }

    for (const [trackName, trackInfo] of Object.entries(apiTracks)) {
      if (trackInfo.id) trackIds[trackName] = trackInfo.id;
      if (trackInfo.color) trackColors[trackName] = trackInfo.color;
      if (trackInfo.radio_channel) trackChannels[trackName] = trackInfo.radio_channel;
      trackActive[trackName] = !!trackInfo.is_active;
      data[trackName] = parseEvents(trackInfo.events, trackInfo.color);

      // Parse subtracks
      if (trackInfo.subtracks && typeof trackInfo.subtracks === "object") {
        trackSubtracks[trackName] = {};
        for (const [subName, subInfo] of Object.entries(trackInfo.subtracks)) {
          trackIds[`${trackName}::${subName}`] = subInfo.id;
          if (subInfo.radio_channel) trackChannels[`${trackName}::${subName}`] = subInfo.radio_channel;
          trackActive[`${trackName}::${subName}`] = !!subInfo.is_active;
          trackSubtracks[trackName][subName] = {
            id: subInfo.id,
            radio_channel: subInfo.radio_channel,
            is_active: !!subInfo.is_active,
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


// ============================================================
// Segment edit popup — inline time editing
// ============================================================

const SEGMENT_EDIT_API = "/cal/api/segment/{id}/edit/";

async function saveSegmentTime(segmentId, field, timeStr) {
  const url = SEGMENT_EDIT_API.replace("{id}", segmentId);
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const body = {};
  body[field] = localHHMMtoISO(timeStr);
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      const msg = data.error || `Failed to update segment (${resp.status})`;
      return { _error: msg };
    }
    return await resp.json();
  } catch (err) {
    console.error("Segment edit error:", err);
    return { _error: "Network error — could not reach server." };
  }
}

function openSegmentEditPopup(segmentId, field, currentValue, eventId, anchorEl) {
  // Remove any existing popup
  const existing = document.getElementById("segEditPopup");
  if (existing) existing.remove();

  const box = document.createElement("div");
  box.id = "segEditPopup";
  box.className = "seg-edit-box";

  // Header
  const header = document.createElement("div");
  header.className = "seg-edit-header";
  const title = document.createElement("span");
  title.className = "seg-edit-title";
  title.textContent = field === "start" ? "Edit Start" : "Edit End";
  header.appendChild(title);
  box.appendChild(header);

  // Flatpickr input
  const input = document.createElement("input");
  input.type = "text";
  input.className = "seg-edit-fp-input";
  box.appendChild(input);

  // Error display
  const errorEl = document.createElement("div");
  errorEl.className = "seg-edit-error";
  box.appendChild(errorEl);

  function showInlineError(msg) {
    errorEl.textContent = msg;
    errorEl.style.display = "block";
    setTimeout(() => { errorEl.style.display = "none"; }, 4000);
  }

  // Button row
  const btnRow = document.createElement("div");
  btnRow.className = "seg-edit-btn-row";

  // "Now" button
  const nowBtn = document.createElement("button");
  nowBtn.className = "seg-pick-pill seg-pick-now";
  nowBtn.textContent = "Now";
  nowBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    box.classList.add("saving");
    const result = await saveSegmentTime(segmentId, field, nowHHMM());
    if (result && result._error) {
      showInlineError(result._error);
      box.classList.remove("saving");
    } else if (result) {
      cleanup();
      await fetchAndLoadData();
      render();
    } else {
      box.classList.remove("saving");
    }
  });
  btnRow.appendChild(nowBtn);

  // "Done" button
  const doneBtn = document.createElement("button");
  doneBtn.className = "seg-pick-pill seg-pick-done";
  doneBtn.textContent = "Done";
  doneBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (input.value && input.value !== currentValue) {
      if (saveTimer) clearTimeout(saveTimer);
      box.classList.add("saving");
      const result = await saveSegmentTime(segmentId, field, input.value);
      if (result && result._error) {
        showInlineError(result._error);
        box.classList.remove("saving");
        return;
      }
      if (result) {
        cleanup();
        await fetchAndLoadData();
        render();
        return;
      }
      box.classList.remove("saving");
    } else {
      cleanup();
    }
  });
  btnRow.appendChild(doneBtn);

  box.appendChild(btnRow);

  document.body.appendChild(box);

  // Parse default time from "HH:MM"
  let defaultDate = null;
  if (currentValue) {
    const parts = currentValue.trim().split(":");
    if (parts.length === 2) {
      const h = parseInt(parts[0], 10);
      const m = parseInt(parts[1], 10);
      if (!isNaN(h) && !isNaN(m)) {
        defaultDate = new Date(2000, 0, 1, h, m);
      }
    }
  }

  // Init Flatpickr in time-only mode
  const fp = flatpickr(input, {
    enableTime: true,
    noCalendar: true,
    dateFormat: "H:i",
    time_24hr: true,
    minuteIncrement: 1,
    defaultDate: defaultDate,
    inline: true,
    onChange: () => {
      // Clear any pending save timer on change
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(doSave, 600);
    },
  });

  let saveTimer = null;
  let saving = false;

  async function doSave() {
    if (saving) return;
    const val = input.value;
    if (!val || val === currentValue) return;
    saving = true;
    box.classList.add("saving");
    const result = await saveSegmentTime(segmentId, field, val);
    if (result && result._error) {
      showInlineError(result._error);
      saving = false;
      box.classList.remove("saving");
    } else if (result) {
      currentValue = val; // update so repeated saves don't re-save same value
      saving = false;
      box.classList.remove("saving");
      await fetchAndLoadData();
      render();
      // Popup is gone after render since DOM is rebuilt
    } else {
      saving = false;
      box.classList.remove("saving");
    }
  }

  // Position next to the anchor element
  const rect = anchorEl.getBoundingClientRect();
  const boxRect = box.getBoundingClientRect();
  let top = rect.bottom + 4 + window.scrollY;
  let left = rect.left + window.scrollX;
  if (left + boxRect.width > window.innerWidth - 8) {
    left = window.innerWidth - boxRect.width - 8 + window.scrollX;
  }
  if (top + boxRect.height > window.innerHeight + window.scrollY - 8) {
    top = rect.top - boxRect.height - 4 + window.scrollY;
  }
  box.style.top = `${top}px`;
  box.style.left = `${left}px`;

  function cleanup() {
    if (saveTimer) clearTimeout(saveTimer);
    fp.destroy();
    box.remove();
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("mousedown", onClickOutside);
  }
  function onClickOutside(e) {
    if (!box.contains(e.target)) {
      // Save on close if value changed
      if (input.value && input.value !== currentValue) {
        if (saveTimer) clearTimeout(saveTimer);
        doSave();
      }
      cleanup();
    }
  }
  setTimeout(() => document.addEventListener("mousedown", onClickOutside), 0);
  function onKey(e) {
    if (e.key === "Escape") cleanup();
    if (e.key === "Enter") {
      e.preventDefault();
      if (saveTimer) clearTimeout(saveTimer);
      doSave();
    }
  }
  document.addEventListener("keydown", onKey);
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
// Quick Add Event Modal
// ============================================================

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
let modalTrackName      = null;

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

  const dateStr = toISODateStr(currentDate);
  let fullFormUrl = `/cal/event/new/?next=/cal/dashboard/&date=${dateStr}`;
  if (trackId) fullFormUrl += `&track=${trackId}`;
  modalFullFormLink.href = fullFormUrl;

  eventPopup.hidden = false;

  const card = anchorEl ? anchorEl.closest(".track-card") : null;
  const anchor = (card || anchorEl) ? (card || anchorEl).getBoundingClientRect() : null;
  if (anchor) {
    const gap = 12;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const boxW = eventPopupBox.offsetWidth;
    const boxH = eventPopupBox.offsetHeight;
    let left = anchor.right + gap;
    if (left + boxW > vw - gap) left = anchor.left - boxW - gap;
    left = Math.max(gap, left);
    let top = anchor.top;
    top = Math.max(gap, Math.min(top, vh - boxH - gap));
    eventPopupBox.style.top = top + "px";
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

async function submitCreateEvent(confirmed) {
  const title = modalTitleInput.value.trim();
  if (!title) return;

  const trackId = parseInt(modalTrackIdInput.value, 10);
  if (!trackId) {
    modalError.textContent = "No track selected.";
    modalError.hidden = false;
    return;
  }

  modalSubmitBtn.disabled = true;
  modalSubmitBtn.textContent = confirmed ? "Pausing & Creating..." : "Creating...";
  modalError.hidden = true;

  try {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    const payload = {
      title: title,
      description: modalDescInput.value.trim(),
      asset_ids: [trackId],
      is_impromptu: true,
    };
    if (confirmed) payload.confirmed = true;

    const resp = await fetch("/cal/api/event/create/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(payload),
    });

    const data = await resp.json().catch(() => ({}));

    if (data.requires_confirmation) {
      // Show confirmation with active event warning
      showConfirmModal(data.message, async () => {
        await submitCreateEvent(true);
      });
      modalSubmitBtn.disabled = false;
      modalSubmitBtn.textContent = "Create";
      return;
    }

    if (resp.ok) {
      closeEventModal();
      showStampToast("Impromptu event created");
      await fetchAndLoadData();
      render();
    } else {
      modalError.textContent = data.error || "Failed to create event.";
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
}

eventModalForm.addEventListener("submit", (e) => {
  e.preventDefault();
  submitCreateEvent(false);
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

  // Mark unapproved events visually
  if (!ev.isApproved) {
    item.classList.add("event-item--unapproved");
  }

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

  // Time info and controls row (scheduled events only)
  if (ev.isScheduled) {
    const actualRow = document.createElement("div");
    actualRow.className = "actual-time-row";

    const schedLabel = document.createElement("span");
    schedLabel.className   = "time-label time-label--scheduled";
    schedLabel.textContent = `Scheduled: ${formatTimeChip(ev.scheduledTime)}`;
    actualRow.appendChild(schedLabel);

    // ── Task #7: Unapproved events show Approve button instead of time controls ──
    if (!ev.isApproved) {
      const pendingLabel = document.createElement("span");
      pendingLabel.className = "time-label time-label--pending";
      pendingLabel.textContent = "PENDING";
      actualRow.appendChild(pendingLabel);

      const approveBtn = document.createElement("button");
      approveBtn.className = "btn btn-xxs btn-approve";
      approveBtn.textContent = "Approve";
      approveBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        await approveEvent(ev.eventId);
      });
      actualRow.appendChild(approveBtn);
    } else {
      // ── Play/Pause/Stop controls + expandable segment list ──
      const segmentInfo = document.createElement("span");
      segmentInfo.className = "time-label time-label--actual";

      const segCount = ev.segments ? ev.segments.length : 0;

      if (ev.isStopped) {
        // Stopped — show summary + undo
        const totalSecs = ev.totalActualSeconds || 0;
        const totalMins = Math.round(totalSecs / 60);
        const startHHMM = ev.actualStart ? isoToLocalHHMM(ev.actualStart) : null;
        const endHHMM = ev.actualEnd ? isoToLocalHHMM(ev.actualEnd) : null;
        if (startHHMM && endHHMM) {
          segmentInfo.textContent = `Stopped: ${startHHMM}\u2013${endHHMM} \u2022 ${formatDuration(totalMins)}`;
        } else {
          segmentInfo.textContent = "Stopped";
        }
        segmentInfo.classList.add("time-label--complete");
        actualRow.appendChild(segmentInfo);

        const undoBtn = document.createElement("button");
        undoBtn.className = "btn btn-xxs btn-undo";
        undoBtn.innerHTML = "&#8630; Undo";
        undoBtn.title = "Undo stop";
        undoBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await stampActualTime(ev.eventId, "undo");
          if (result) { await fetchAndLoadData(); render(); }
        });
        actualRow.appendChild(undoBtn);
      } else if (ev.isCurrentlyActive) {
        // Currently playing — show Pause + Stop
        const openSeg = ev.segments.find(s => s.end === null);
        const activeStart = openSeg ? isoToLocalHHMM(openSeg.start) : null;
        segmentInfo.innerHTML = `Active since ${activeStart || "?"}`;
        if (segCount > 1) segmentInfo.innerHTML += ` (${segCount} seg)`;
        segmentInfo.classList.add("time-label--active");
        actualRow.appendChild(segmentInfo);

        const pauseBtn = document.createElement("button");
        pauseBtn.className = "btn btn-xxs btn-pause";
        pauseBtn.innerHTML = "&#10074;&#10074; Pause";
        pauseBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await stampActualTime(ev.eventId, "pause");
          if (result) { await fetchAndLoadData(); render(); }
        });
        actualRow.appendChild(pauseBtn);

        const stopBtn = document.createElement("button");
        stopBtn.className = "btn btn-xxs btn-stop";
        stopBtn.innerHTML = "&#9632; Stop";
        stopBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await stampActualTime(ev.eventId, "stop");
          if (result) { await fetchAndLoadData(); render(); }
        });
        actualRow.appendChild(stopBtn);

        const undoBtn = document.createElement("button");
        undoBtn.className = "btn btn-xxs btn-undo";
        undoBtn.innerHTML = "&#8630; Undo";
        undoBtn.title = "Undo last stamp";
        undoBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await stampActualTime(ev.eventId, "undo");
          if (result) { await fetchAndLoadData(); render(); }
        });
        actualRow.appendChild(undoBtn);
      } else if (segCount > 0) {
        // Has segments but not active (paused)
        const totalSecs = ev.totalActualSeconds || 0;
        const totalMins = Math.round(totalSecs / 60);
        segmentInfo.textContent = `Paused (${segCount} seg \u2022 ${formatDuration(totalMins)})`;
        segmentInfo.classList.add("time-label--paused");
        actualRow.appendChild(segmentInfo);

        const playBtn = document.createElement("button");
        playBtn.className = "btn btn-xxs btn-play";
        playBtn.innerHTML = "&#9654; Resume";
        playBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await stampActualTime(ev.eventId, "play");
          if (result) { await fetchAndLoadData(); render(); }
        });
        actualRow.appendChild(playBtn);

        const undoBtn = document.createElement("button");
        undoBtn.className = "btn btn-xxs btn-undo";
        undoBtn.innerHTML = "&#8630; Undo";
        undoBtn.title = "Undo last stamp";
        undoBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await stampActualTime(ev.eventId, "undo");
          if (result) { await fetchAndLoadData(); render(); }
        });
        actualRow.appendChild(undoBtn);
      } else {
        // No segments — show Play
        segmentInfo.textContent = "Actual: \u2014";
        actualRow.appendChild(segmentInfo);

        const playBtn = document.createElement("button");
        playBtn.className = "btn btn-xxs btn-play";
        playBtn.innerHTML = "&#9654; Play";
        playBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const result = await stampActualTime(ev.eventId, "play");
          if (result) { await fetchAndLoadData(); render(); }
        });
        actualRow.appendChild(playBtn);
      }

      // ── Expandable segment list (when segments exist) ──
      if (segCount > 0) {
        const segToggle = document.createElement("button");
        segToggle.className = "btn btn-xxs btn-seg-toggle";
        segToggle.textContent = `${segCount} seg`;
        segToggle.title = "Show/hide segments";
        actualRow.appendChild(segToggle);

        const segList = document.createElement("div");
        segList.className = "segment-list hidden";

        ev.segments.forEach((seg, i) => {
          const row = document.createElement("div");
          row.className = "segment-row";

          const label = document.createElement("span");
          label.className = "segment-label";
          label.textContent = `Seg ${i + 1}:`;
          row.appendChild(label);

          const startTime = document.createElement("span");
          startTime.className = "editable-time";
          startTime.textContent = isoToLocalHHMM(seg.start) || "?";
          startTime.title = "Click to edit start time";
          startTime.addEventListener("click", (e) => {
            e.stopPropagation();
            openSegmentEditPopup(seg.id, "start", startTime.textContent, ev.eventId, startTime);
          });
          row.appendChild(startTime);

          const dash = document.createElement("span");
          dash.className = "segment-dash";
          dash.textContent = "\u2013";
          row.appendChild(dash);

          const endTime = document.createElement("span");
          endTime.className = "editable-time";
          endTime.textContent = seg.end ? isoToLocalHHMM(seg.end) : (ev.isCurrentlyActive && !seg.end ? "now" : "\u2014");
          endTime.title = seg.end ? "Click to edit end time" : "";
          if (seg.end) {
            endTime.addEventListener("click", (e) => {
              e.stopPropagation();
              openSegmentEditPopup(seg.id, "end", endTime.textContent, ev.eventId, endTime);
            });
          } else {
            endTime.classList.add("editable-time--disabled");
          }
          row.appendChild(endTime);

          // Show segment duration
          if (seg.end) {
            const segStart = isoToLocalHHMM(seg.start);
            const segEnd = isoToLocalHHMM(seg.end);
            const dur = durationMinutes(segStart, segEnd);
            if (dur != null) {
              const durSpan = document.createElement("span");
              durSpan.className = "segment-dur";
              durSpan.textContent = formatDuration(dur);
              row.appendChild(durSpan);
            }
          }

          segList.appendChild(row);
        });

        actualRow.appendChild(segList);

        segToggle.addEventListener("click", (e) => {
          e.stopPropagation();
          segList.classList.toggle("hidden");
          segToggle.classList.toggle("active");
        });
      }
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


// ============================================================
// Approve event (Task #7)
// ============================================================

async function approveEvent(eventId) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  try {
    const resp = await fetch(`/cal/api/event/${eventId}/approve/`, {
      method: "POST",
      headers: { "X-CSRFToken": csrf },
    });
    const result = await resp.json();
    if (result.approved) {
      await fetchAndLoadData();
      render();
    } else if (result.error) {
      showStampToast(result.error);
    }
  } catch (err) {
    console.error("Approve error:", err);
    showStampToast("Network error — could not approve event.");
  }
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

    // Active/Inactive toggle — red border on active tracks
    // Also activate when any event (parent or subtrack) is currently active
    const hasActiveEvent = (entries || []).some(e => e.isCurrentlyActive) ||
      Object.values(trackSubtracks[trackName] || {}).some(sub =>
        (sub.events || []).some(e => e.isCurrentlyActive)
      );
    if (trackActive[trackName] || hasActiveEvent) {
      card.classList.add("track-card--active");
    }
    const activeToggleBtn = card.querySelector(".active-toggle-btn");
    if (activeToggleBtn) {
      if (trackActive[trackName] || hasActiveEvent) {
        activeToggleBtn.classList.add("active");
        activeToggleBtn.textContent = "Active";
      } else {
        activeToggleBtn.textContent = "Inactive";
      }
      activeToggleBtn.addEventListener("click", async () => {
        const trackId = trackIds[trackName];
        if (!trackId) return;
        const newState = !trackActive[trackName];
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
        const resp = await fetch(`/cal/api/track/${trackId}/active/`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
          body: JSON.stringify({ is_active: newState }),
        });
        if (resp.ok) {
          const result = await resp.json();
          trackActive[trackName] = result.is_active;
          render();
        } else {
          showStampToast("Failed to toggle track active state");
        }
      });
    }

    // Radio channel dropdown (track-level, persisted server-side)
    const channelSelect = card.querySelector(".radio-channel-select");
    const chVal = trackChannels[trackName];
    if (chVal) channelSelect.value = String(chVal);
    channelSelect.setAttribute("data-empty", chVal ? "false" : "true");
    channelSelect.addEventListener("change", async () => {
      const val = channelSelect.value;
      channelSelect.setAttribute("data-empty", val ? "false" : "true");
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
    const noteForm       = card.querySelector(".note-form");
    const cancelNoteBtn  = card.querySelector(".cancel-note");
    const quickAddBtn    = card.querySelector(".add-event-btn");
    const eventsListEl   = card.querySelector(".events-list");
    const notesListEl    = card.querySelector(".notes-list");

    on(quickAddBtn, "click", (e) => {
      openEventModal(trackName, trackIds[trackName], e.target);
    });
    on(cancelNoteBtn, "click", () => noteForm?.classList.add("hidden"));

    // Separate events from track-level notes
    const events = sortEvents(
      entries.filter(e => e.desc && e.time !== undefined && e.desc !== "__TRACK_NOTE__")
    );
    const notes = entries.filter(e => e.desc === "__TRACK_NOTE__");

    // Filter logic — text search + unapproved toggle (Task #9)
    let matchesFilter = !normalizedFilter;
    const filteredEvents = events.filter((e) => {
      // Hide unapproved events when toggle is off
      if (!showUnapproved && !e.isApproved) return false;
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
        subChSelect.setAttribute("data-empty", subChVal ? "false" : "true");
        subChSelect.addEventListener("change", async () => {
          const val = subChSelect.value;
          subChSelect.setAttribute("data-empty", val ? "false" : "true");
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

        // Subtrack "+" button — open quick-add modal for this subtrack
        const subAddBtn = subSection.querySelector(".subtrack-add-btn");
        if (subAddBtn) {
          const subTrackId = trackIds[subChKey] || subInfo.id;
          subAddBtn.addEventListener("click", (e) => {
            openEventModal(subName, subTrackId, e.target);
          });
        }

        // Subtrack events — same rendering as parent track events (with unapproved filter)
        const subEventsList = subSection.querySelector(".subtrack-events-list");
        const subEvents = sortEvents((subInfo.events || []).filter(e => showUnapproved || e.isApproved));
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

// ============================================================
// Unapproved toggle (Task #9)
// ============================================================

function initUnapprovedToggle() {
  // Read initial state from URL
  const params = new URLSearchParams(window.location.search);
  if (params.has("show_unapproved")) {
    showUnapproved = params.get("show_unapproved") !== "0";
  }
  const toggle = document.getElementById("show-unapproved-toggle");
  if (toggle) {
    toggle.checked = showUnapproved;
    toggle.addEventListener("change", () => {
      showUnapproved = toggle.checked;
      syncUnapprovedToURL();
      render();
    });
  }
}

function syncUnapprovedToURL() {
  const url = new URL(window.location);
  if (showUnapproved) {
    url.searchParams.delete("show_unapproved");
  } else {
    url.searchParams.set("show_unapproved", "0");
  }
  history.replaceState(null, "", url.toString());
}


// ============================================================
// Boot — fetch from server, then render
// ============================================================

// ── Snap grid width to fit exact columns (no extra stretch) ──
function snapGridWidth() {
  const colWidth = 350, gap = 18, pad = 40; // pad = grid padding L+R
  const avail = window.innerWidth - pad;
  const cols = Math.max(1, Math.floor((avail + gap) / (colWidth + gap)));
  grid.style.maxWidth = (cols * colWidth + (cols - 1) * gap + pad) + "px";
}
window.addEventListener("resize", snapGridWidth);

(async function init() {
  initDateNav();
  initUnapprovedToggle();
  updateDateDisplay();
  snapGridWidth();
  await fetchAndLoadData();
  render();
})();
