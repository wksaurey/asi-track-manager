# Post-Deploy Verification

Run these checks **against the production server** after deploying. See [`PRE_DEPLOY.md`](PRE_DEPLOY.md) for pre-deploy checks on your dev machine.

**Target:** ASI Track Manager on `http://test-scl-mobius00.asi.asirobots.com` (or the server's IP)

**CRITICAL: This is a PRODUCTION environment with real data.**
- Do NOT delete, edit, or modify any existing events, assets, or users.
- Any test data you create MUST be cleaned up before the test is complete.
- Do NOT change any settings, toggle any admin flags, or approve/unapprove existing events.

Use the admin account credentials provided to you. Report PASS/FAIL for each test, and a summary at the end.

**Precondition:** Use a private/incognito browser window. This ensures a clean session (no existing login, no cached localStorage for dark mode or Gantt state).

---

## Test 1: Static Files & Login

1. Navigate to the site root URL. Confirm it redirects to the login page (if already logged in, go to `/users/logout/` first).
2. Verify the login page renders correctly — CSS is loaded (styled form, not raw HTML), Bootstrap is working.
3. Log in with the admin credentials.
4. Confirm redirect to the calendar day view (`/cal/calendar/`).

**PASS criteria:** Page is styled, no broken CSS/JS, login succeeds.

---

## Test 2: Calendar Views

1. On the calendar page, confirm the **day view** loads by default with the Gantt timeline.
2. Switch to **week view** — verify it renders a weekly grid.
3. Switch to **month view** — verify it renders a monthly calendar.
4. Navigate forward and backward using the prev/next arrows in each view.
5. Return to day view. Verify the red "Now" line appears if viewing today.

**PASS criteria:** All three views render without errors, navigation works.

---

## Test 3: Asset Pages

1. Navigate to `/cal/assets/`.
2. Verify the asset list loads showing tracks, vehicles, and operators.
3. Click on any track to view its detail/schedule page.
4. Confirm the page loads without errors.

**PASS criteria:** Asset list and detail pages render correctly.

---

## Test 4: Dashboard

1. Navigate to `/cal/dashboard/`.
2. Verify the dashboard loads with track timelines.
3. Confirm radio channel dropdowns are visible on track headers.
4. Do NOT click Start/Stop/Pause on any existing events.
5. Do NOT change any radio channel values.

**PASS criteria:** Dashboard renders, track timelines visible, no JS errors in console.

---

## Test 5: Event Creation & Cleanup

**This test creates a temporary event. You MUST delete it at the end.**

1. Navigate to `/cal/event/new/`.
2. Create a test event:
   - Title: `SMOKE TEST — DELETE ME`
   - Date: tomorrow's date
   - Start time: `08:00`
   - End time: `09:00`
   - Select any one track
   - Leave description as: `Automated smoke test. Safe to delete.`
3. Submit the form.
4. Verify the event appears on the calendar (navigate to tomorrow in day view).
5. Click the event to open the edit page. Verify all fields populated correctly.
6. **CLEANUP:** Delete the test event using the delete button on the edit page. Confirm deletion.
7. Verify the event no longer appears on the calendar.

**PASS criteria:** Create, view, edit page load, and delete all work. Event is fully cleaned up.

---

## Test 6: Pending Events & Approval Page

1. Navigate to `/cal/events/pending/`.
2. Verify the page loads (it may show existing pending events or be empty — both are fine).
3. Do NOT approve or reject any existing events.

**PASS criteria:** Pending events page renders without errors.

---

## Test 7: User Management (Admin Only)

1. Navigate to `/users/management/`.
2. Verify the user list loads.
3. Do NOT toggle admin status or delete any users.

**PASS criteria:** User management page renders, shows user list.

---

## Test 8: Profile Page

1. Navigate to `/users/profile/`.
2. Verify the profile edit form loads with the current user's information.
3. Do NOT save any changes.

**PASS criteria:** Profile page renders with current user data.

---

## Test 9: API Endpoints

Open the browser's developer console (F12 → Console tab) and run each of these. Verify each returns a 200 status with JSON data:

```javascript
// Dashboard events API
fetch('/cal/api/dashboard-events/').then(r => { console.log('dashboard-events:', r.status); return r.json(); }).then(d => console.log('  events count:', Object.keys(d).length));

// Analytics API
fetch('/cal/api/analytics/').then(r => { console.log('analytics:', r.status); return r.json(); }).then(d => console.log('  data:', typeof d));
```

**PASS criteria:** Both return HTTP 200 with valid JSON.

---

## Test 10: Mobile Responsiveness

1. Open browser DevTools (F12) and toggle device toolbar (Ctrl+Shift+M).
2. Set viewport to 375px wide (iPhone size).
3. Verify:
   - Hamburger menu appears and opens/closes correctly.
   - Calendar day view is usable (can scroll, events visible).
   - Dashboard renders without horizontal overflow.
4. Set viewport to 768px (tablet). Verify layout adapts.
5. Close DevTools / restore normal viewport.

**PASS criteria:** Layout adapts at both breakpoints, no broken overflow.

---

## Summary Template

Report results in this format:

```
PRODUCTION SMOKE TEST RESULTS — [date]
Target: [URL used]

Test 1 — Static Files & Login:    [PASS/FAIL] [notes if fail]
Test 2 — Calendar Views:          [PASS/FAIL]
Test 3 — Asset Pages:             [PASS/FAIL]
Test 4 — Dashboard:               [PASS/FAIL]
Test 5 — Event Create & Cleanup:  [PASS/FAIL] [confirm test event deleted]
Test 6 — Pending Events Page:     [PASS/FAIL]
Test 7 — User Management:         [PASS/FAIL]
Test 8 — Profile Page:            [PASS/FAIL]
Test 9 — API Endpoints:           [PASS/FAIL]
Test 10 — Mobile Responsiveness:  [PASS/FAIL]

Overall: [X/10 PASSED]
Cleanup confirmed: [YES/NO — test event from Test 5 deleted]
```

If any test fails, include the error message, screenshot, or console output.
