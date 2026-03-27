# ASI Track Manager v1.1 — QA Test Plan

**Version:** 1.1
**Date:** 2026-03-27
**Prepared by:** QA Team
**App URL:** http://localhost:8000

## Prerequisites

Before starting QA, set up the test environment:

```bash
# Activate virtual environment
. ./.venv/asi-track-manager/bin/activate

# Run migrations
python3 manage.py migrate

# Load test data (creates admin user, regular user, tracks, vehicles, sample events)
python3 manage.py setup_testdb --days 7

# Start the dev server
python3 manage.py runserver
```

**Test Accounts:**
- **Admin:** username `admin`, password `admin` (is_staff=True)
- **Regular User:** username `kolter`, password `testpass123`
- To create additional users, use the Register page at `/users/register/`

---

## Category 1: Timezone Verification

All times should display in Eastern Time (America/New_York). The system stores times internally in UTC but should always present them to users in ET.

---

### QA-001: Create Event — Time Displays Correctly

**ID:** QA-001
**Category:** Timezone
**Preconditions:** Logged in as any user. At least one track asset exists.
**Steps:**
1. Navigate to `/cal/event/new/`
2. Enter title "Timezone Test 9AM"
3. Set start time to 9:00 AM today
4. Set end time to 11:00 AM today
5. Select a track asset
6. Click Save
7. Navigate to the calendar day view for today

**Expected Result:**
- The event appears on the day view Gantt chart at the 9:00 AM position
- The time label on the event block reads "9:00 AM" (or "9:00-11:00 AM")
- The event is NOT shifted to 1:00 PM or 2:00 PM (which would indicate UTC display)

**Pass/Fail:** [ ]

---

### QA-002: Late Night Event — Correct Day

**ID:** QA-002
**Category:** Timezone
**Preconditions:** Logged in as any user.
**Steps:**
1. Create a new event with start time 11:00 PM today, end time 12:30 AM tomorrow
2. Select a track and save
3. Navigate to the day view for today
4. Navigate to the day view for tomorrow

**Expected Result:**
- The event appears on today's day view (where 11 PM was entered)
- The event does NOT appear on tomorrow's view as if it was a different-day event
- Note: If the event spans midnight, it may reasonably appear on both days, but the primary day should be today

**Pass/Fail:** [ ]

---

### QA-003: Day View Gantt — Event Position at 2 PM

**ID:** QA-003
**Category:** Timezone
**Preconditions:** Logged in. An event exists at 2:00 PM - 4:00 PM on a specific date.
**Steps:**
1. Create or confirm an event at 2:00 PM - 4:00 PM
2. Navigate to the day view for that date
3. Visually inspect the Gantt chart

**Expected Result:**
- The event block starts at the 2 PM axis marker
- The event block ends at the 4 PM axis marker
- The block does NOT appear at the 6 PM or 7 PM position (UTC offset error)

**Pass/Fail:** [ ]

---

### QA-004: Week View — Events on Correct Day

**ID:** QA-004
**Category:** Timezone
**Preconditions:** Logged in. Events exist on known dates.
**Steps:**
1. Create an event at 10:00 PM on Wednesday
2. Navigate to the week view for that week
3. Check which day column the event appears in

**Expected Result:**
- The event appears in the Wednesday column
- It does NOT appear in the Thursday column (which would happen if UTC date were used and the Eastern time crossed midnight UTC)

**Pass/Fail:** [ ]

---

### QA-005: Month View — Event Times Display Correctly

**ID:** QA-005
**Category:** Timezone
**Preconditions:** Logged in. Events exist in the current month.
**Steps:**
1. Navigate to the month view
2. Click on a day cell that has events
3. Read the time displayed on event tiles

**Expected Result:**
- Event times show Eastern Time values (e.g., "2:00-4:00 PM")
- Times do NOT show UTC values (which would be 4-5 hours ahead)

**Pass/Fail:** [ ]

---

### QA-006: "Now" Red Line — Matches Current Time

**ID:** QA-006
**Category:** Timezone
**Preconditions:** Logged in. Viewing today's day view.
**Steps:**
1. Navigate to the day view for today
2. Note the current actual Eastern Time
3. Observe the red "Now" line on the Gantt chart

**Expected Result:**
- The "Now" line is positioned at the current Eastern Time
- If it is 2:30 PM ET, the line should be between the 2 PM and 3 PM markers
- The line should NOT be at the UTC equivalent (e.g., 6:30 PM if EDT)

**Pass/Fail:** [ ]

---

### QA-007: Dashboard — Event Times Match Entered Values

**ID:** QA-007
**Category:** Timezone
**Preconditions:** Logged in as admin. Approved events exist for today.
**Steps:**
1. Navigate to `/cal/dashboard/`
2. Observe event blocks on the timeline
3. Compare displayed times with what was originally entered

**Expected Result:**
- Event times on the dashboard match the times that were entered when creating the event
- No UTC offset is apparent

**Pass/Fail:** [ ]

---

### QA-008: Event Edit Form — Shows Originally Entered Time

**ID:** QA-008
**Category:** Timezone
**Preconditions:** An event was created with start time 9:00 AM, end time 11:00 AM.
**Steps:**
1. Navigate to the event's edit page
2. Observe the start_time and end_time form fields

**Expected Result:**
- Start time field shows 9:00 AM (or the date-time equivalent)
- End time field shows 11:00 AM
- Values are NOT shown in UTC

**Pass/Fail:** [ ]

---

### QA-009: DST Transition — Spring Forward

**ID:** QA-009
**Category:** Timezone
**Preconditions:** Logged in. (Best tested near a DST transition date, but can be simulated.)
**Steps:**
1. Create an event on the day after DST spring-forward (second Sunday of March)
2. Set start time to 3:00 PM
3. Save and view on the day view

**Expected Result:**
- The event appears at 3:00 PM on the Gantt chart
- No off-by-one-hour error due to DST transition
- The event is on the correct date

**Pass/Fail:** [ ]

---

### QA-010: Midnight Edge Case — No Date Shift

**ID:** QA-010
**Category:** Timezone
**Preconditions:** Logged in.
**Steps:**
1. Create an event at 12:00 AM (midnight) tomorrow, ending at 2:00 AM
2. Navigate to the day view for tomorrow

**Expected Result:**
- The event appears on tomorrow's day view
- The event does NOT appear on today's day view as a separate event
- If the Gantt chart starts at 6 AM, the midnight event may not be visible in the Gantt area (this is expected — it is outside the 6 AM - 8 PM display range)

**Pass/Fail:** [ ]

---

## Category 2: Feedback Feature

The feedback feature adds a floating button on all authenticated pages that opens a modal for submitting bug reports, feature requests, and general feedback.

---

### QA-011: Feedback Button — Visible When Logged In

**ID:** QA-011
**Category:** Feedback
**Preconditions:** Logged in as any user.
**Steps:**
1. Navigate to `/cal/calendar/`
2. Look for a floating feedback button (typically bottom-right corner)

**Expected Result:**
- A feedback button (icon or text) is visible on the page
- It floats above other content and remains visible when scrolling

**Pass/Fail:** [ ]

---

### QA-012: Feedback Button — NOT Visible When Logged Out

**ID:** QA-012
**Category:** Feedback
**Preconditions:** Not logged in.
**Steps:**
1. Navigate to `/users/login/`
2. Look for the feedback button

**Expected Result:**
- The feedback button is NOT visible on the login page
- It is NOT visible on the registration page either

**Pass/Fail:** [ ]

---

### QA-013: Feedback Modal — Opens on Click

**ID:** QA-013
**Category:** Feedback
**Preconditions:** Logged in as any user.
**Steps:**
1. Click the feedback button

**Expected Result:**
- A modal dialog opens
- The modal contains a form with:
  - Category dropdown/select (Bug, Feature, Other)
  - Message text area
  - Submit button
- The page URL is auto-populated (hidden or visible)

**Pass/Fail:** [ ]

---

### QA-014: Feedback Submission — Success Toast

**ID:** QA-014
**Category:** Feedback
**Preconditions:** Logged in. Feedback modal is open.
**Steps:**
1. Select category "Bug"
2. Enter message "The calendar takes too long to load"
3. Click Submit

**Expected Result:**
- The modal closes
- A success toast/notification appears (e.g., "Feedback submitted, thank you!")
- The page does not reload

**Pass/Fail:** [ ]

---

### QA-015: Feedback Submission — Validation Errors

**ID:** QA-015
**Category:** Feedback
**Preconditions:** Logged in. Feedback modal is open.
**Steps:**
1. Leave the message field empty
2. Click Submit

**Expected Result:**
- The form does not submit
- A validation error message appears (e.g., "Message is required")
- The modal remains open

**Pass/Fail:** [ ]

---

### QA-016: Feedback — Visible in Django Admin

**ID:** QA-016
**Category:** Feedback
**Preconditions:** A feedback entry has been submitted (from QA-014). Logged in as admin.
**Steps:**
1. Navigate to `/admin/` (Django admin)
2. Find the Feedback model section
3. Click to view feedback entries

**Expected Result:**
- The submitted feedback entry appears in the list
- It shows the correct:
  - Username of the submitter
  - Category ("Bug")
  - Message text
  - Page URL where it was submitted from
  - Timestamp

**Pass/Fail:** [ ]

---

### QA-017: Feedback — page_url Auto-Captured

**ID:** QA-017
**Category:** Feedback
**Preconditions:** Logged in.
**Steps:**
1. Navigate to `/cal/assets/`
2. Open the feedback modal
3. Submit feedback with category "Feature" and message "Add bulk import"
4. Check the feedback entry in Django admin

**Expected Result:**
- The page_url field on the saved feedback is `/cal/assets/` (the page where the button was clicked)
- The page_url is NOT `/cal/calendar/` or any other page

**Pass/Fail:** [ ]

---

### QA-018: Feedback — All Three Categories Work

**ID:** QA-018
**Category:** Feedback
**Preconditions:** Logged in.
**Steps:**
1. Submit feedback with category "Bug" and message "Bug test"
2. Submit feedback with category "Feature" and message "Feature test"
3. Submit feedback with category "Other" and message "Other test"
4. Check Django admin for all three entries

**Expected Result:**
- All three entries are saved with correct categories
- No errors during submission of any category

**Pass/Fail:** [ ]

---

### QA-019: Feedback Modal — Close Without Submitting

**ID:** QA-019
**Category:** Feedback
**Preconditions:** Logged in.
**Steps:**
1. Open the feedback modal
2. Type something in the message field
3. Close the modal (click X, click outside, or press Escape)
4. Check Django admin

**Expected Result:**
- No new feedback entry is created
- The modal closes cleanly
- The typed text is discarded (or preserved for convenience, either is acceptable)

**Pass/Fail:** [ ]

---

### QA-020: Feedback — Submit From Multiple Pages

**ID:** QA-020
**Category:** Feedback
**Preconditions:** Logged in.
**Steps:**
1. Navigate to `/cal/calendar/` and submit feedback
2. Navigate to `/cal/assets/` and submit feedback
3. Navigate to `/cal/event/new/` and submit feedback
4. Check all three entries in Django admin

**Expected Result:**
- Each entry has the correct page_url corresponding to where it was submitted
- Entry 1: `/cal/calendar/`
- Entry 2: `/cal/assets/`
- Entry 3: `/cal/event/new/`

**Pass/Fail:** [ ]

---

## Category 3: Day View Scrolling

The day view Gantt chart should auto-scroll to show the most relevant content (current events or current time) when the page loads.

---

### QA-021: Auto-Scroll — Shows Current Time Area

**ID:** QA-021
**Category:** Day View
**Preconditions:** Logged in. Viewing today's day view.
**Steps:**
1. Navigate to the day view for today
2. Observe where the view is scrolled to on page load

**Expected Result:**
- The view auto-scrolls so the current time area is visible
- If it is 2:00 PM, the 2 PM mark should be visible without manual scrolling
- The view does NOT start at 6:00 AM (the leftmost position) if there is content later in the day

**Pass/Fail:** [ ]

---

### QA-022: Manual Scroll — Left/Right Navigation

**ID:** QA-022
**Category:** Day View
**Preconditions:** Logged in. Day view is displayed.
**Steps:**
1. Scroll the Gantt area to the left
2. Scroll the Gantt area to the right

**Expected Result:**
- Earlier hours (6 AM, 7 AM) become visible when scrolling left
- Later hours (6 PM, 7 PM, 8 PM) become visible when scrolling right
- Scrolling is smooth and responsive

**Pass/Fail:** [ ]

---

### QA-023: Sticky Track Labels

**ID:** QA-023
**Category:** Day View
**Preconditions:** Logged in. Day view with multiple tracks. View is scrolled horizontally.
**Steps:**
1. Navigate to the day view with at least 3 tracks visible
2. Scroll the Gantt area horizontally to the right

**Expected Result:**
- Track name labels on the left side remain visible (sticky) while scrolling
- Track labels do NOT scroll off-screen with the timeline content
- Labels remain aligned with their corresponding track rows

**Pass/Fail:** [ ]

---

### QA-024: Event Blocks — Correct Time Span

**ID:** QA-024
**Category:** Day View
**Preconditions:** An event exists from 10:00 AM to 2:00 PM (4 hours).
**Steps:**
1. Navigate to the day view for the event's date
2. Inspect the event block visually

**Expected Result:**
- The event block starts at the 10 AM axis marker
- The event block ends at the 2 PM axis marker
- The block width represents exactly 4 hours of the timeline

**Pass/Fail:** [ ]

---

### QA-025: "Now" Line — Visible and Positioned

**ID:** QA-025
**Category:** Day View
**Preconditions:** Logged in. Viewing today's day view.
**Steps:**
1. Navigate to the day view for today
2. Look for the red "Now" line

**Expected Result:**
- A red vertical line is visible at the current time position
- The line spans from the axis row through all track rows
- A "Now" label is visible near the line
- The line updates position over time (check after 1-2 minutes)

**Pass/Fail:** [ ]

---

### QA-026: No Events — Centers on Current Time

**ID:** QA-026
**Category:** Day View
**Preconditions:** Logged in. No events exist for today (or a specific date with no events).
**Steps:**
1. Navigate to the day view for a date with no events

**Expected Result:**
- If viewing today: the view auto-scrolls to center on the current time
- If viewing another date: the view shows a reasonable default position (e.g., start of business hours, 8-9 AM area)
- The page does NOT crash or show an error

**Pass/Fail:** [ ]

---

### QA-027: Early Morning Events — Scroll to Event Area

**ID:** QA-027
**Category:** Day View
**Preconditions:** An event exists at 6:30 AM on a specific date.
**Steps:**
1. Navigate to the day view for that date

**Expected Result:**
- The view auto-scrolls to show the 6:30 AM area where the event is
- The event block is visible without requiring manual scrolling
- The 6 AM axis marker should be near the left edge of the visible area

**Pass/Fail:** [ ]

---

### QA-028: Responsive — Narrow Browser Window

**ID:** QA-028
**Category:** Day View
**Preconditions:** Logged in. Day view is displayed.
**Steps:**
1. Resize the browser window to approximately 768px wide (tablet width)
2. Observe the day view Gantt chart
3. Scroll horizontally

**Expected Result:**
- The Gantt chart is still scrollable horizontally
- Track labels remain readable
- Event blocks are still visible and clickable
- No horizontal overflow causes layout issues on the rest of the page

**Pass/Fail:** [ ]

---

### QA-029: Axis Hour Markers — Full Range

**ID:** QA-029
**Category:** Day View
**Preconditions:** Logged in. Day view is displayed.
**Steps:**
1. Navigate to any day view
2. Scroll through the full timeline from left to right
3. Count/note the hour markers

**Expected Result:**
- Hour markers appear for: 6am, 7am, 8am, 9am, 10am, 11am, 12pm, 1pm, 2pm, 3pm, 4pm, 5pm, 6pm, 7pm, 8pm
- All 15 markers are present
- They are evenly spaced

**Pass/Fail:** [ ]

---

### QA-030: Click Event in Scrolled View — Navigates Correctly

**ID:** QA-030
**Category:** Day View
**Preconditions:** Events exist on the day view.
**Steps:**
1. Navigate to the day view
2. Scroll to find an event
3. Click on the event block

**Expected Result:**
- The browser navigates to the event's edit page (`/cal/event/edit/<id>/`)
- The correct event is loaded (title matches what was clicked)
- The Back button on the edit page returns to the day view

**Pass/Fail:** [ ]

---

## Category 4: Event Visibility

Non-owner users should be able to view (but not edit) other users' event reservations. Creator names should be visible on calendar views.

---

### QA-031: Create Event as User A

**ID:** QA-031
**Category:** Event Visibility
**Preconditions:** Two user accounts exist (User A and User B).
**Steps:**
1. Log in as User A
2. Create an event: title "User A's Test", 10 AM - 12 PM today, select a track
3. Save the event
4. Note the event ID from the URL

**Expected Result:**
- Event is created successfully
- Event appears on the calendar
- Event shows "Created by User A" metadata

**Pass/Fail:** [ ]

---

### QA-032: User B Sees User A's Event on Calendar

**ID:** QA-032
**Category:** Event Visibility
**Preconditions:** Event from QA-031 exists. User B is a different regular user.
**Steps:**
1. Log out of User A
2. Log in as User B
3. Navigate to the calendar day view for the event's date

**Expected Result:**
- User A's event is visible on the calendar
- The event block shows the event title "User A's Test"
- User A's name is visible on or near the event

**Pass/Fail:** [ ]

---

### QA-033: User B — Read-Only View (Not Redirect)

**ID:** QA-033
**Category:** Event Visibility
**Preconditions:** Logged in as User B. User A's event exists.
**Steps:**
1. Click on User A's event in the calendar (or navigate directly to `/cal/event/edit/<id>/`)

**Expected Result:**
- User B sees the event detail page (HTTP 200)
- User B is NOT redirected to the calendar (no HTTP 302)
- The page loads with the event's information visible

**Pass/Fail:** [ ]

---

### QA-034: Read-Only View — Form Fields Disabled

**ID:** QA-034
**Category:** Event Visibility
**Preconditions:** User B is viewing User A's event (from QA-033).
**Steps:**
1. Inspect the form fields on the event page

**Expected Result:**
- All form fields (title, description, start time, end time, assets) are disabled/readonly
- User B cannot type in the title field
- User B cannot change the date/time pickers
- User B cannot modify the asset selection

**Pass/Fail:** [ ]

---

### QA-035: Read-Only View — No Save/Delete Buttons

**ID:** QA-035
**Category:** Event Visibility
**Preconditions:** User B is viewing User A's event.
**Steps:**
1. Look for Save and Delete buttons on the page

**Expected Result:**
- There is NO Save button visible
- There is NO Delete button visible
- The action bar at the bottom of the form is either hidden or only shows a Back button

**Pass/Fail:** [ ]

---

### QA-036: Read-Only View — Creator Banner

**ID:** QA-036
**Category:** Event Visibility
**Preconditions:** User B is viewing User A's event.
**Steps:**
1. Look for a banner or message indicating whose event this is

**Expected Result:**
- A banner or message says something like "Viewing [User A]'s reservation" or "Created by [User A]"
- The banner clearly communicates that this is a read-only view of someone else's event

**Pass/Fail:** [ ]

---

### QA-037: User B — Cannot Submit Edits via POST

**ID:** QA-037
**Category:** Event Visibility
**Preconditions:** User B has the event edit page open. (This is a security test.)
**Steps:**
1. Using browser developer tools, remove the `disabled` attribute from form fields
2. Change the title to "Hacked by User B"
3. Submit the form (find/create a submit button via dev tools if needed)

**Expected Result:**
- The form submission is rejected (redirected or returns an error)
- The event title in the database remains unchanged ("User A's Test")
- User B cannot bypass the read-only restriction via direct POST

**Pass/Fail:** [ ]

---

### QA-038: Creator Name — Visible on Month/Week Views

**ID:** QA-038
**Category:** Event Visibility
**Preconditions:** Events exist created by different users. Logged in as any user.
**Steps:**
1. Navigate to the month view
2. Look at event tiles on day cells
3. Navigate to the week view
4. Look at event entries in the track grid

**Expected Result:**
- Each event shows the creator's username somewhere in the event tile
- The creator name is readable and does not break the layout
- Different users' events show different creator names

**Pass/Fail:** [ ]

---

### QA-039: Creator Name — Visible in Day View Gantt Tooltip

**ID:** QA-039
**Category:** Event Visibility
**Preconditions:** Events exist on a specific date. Logged in.
**Steps:**
1. Navigate to the day view
2. Hover over an event block (or inspect the tooltip/title attribute)

**Expected Result:**
- The event block's tooltip (title attribute) or the block text includes the creator's username
- Example: "Sprint Test (by kolter)" or the username appears in the block text

**Pass/Fail:** [ ]

---

### QA-040: Admin — Can Still Edit Any User's Events

**ID:** QA-040
**Category:** Event Visibility
**Preconditions:** User A created an event. Logged in as admin.
**Steps:**
1. Navigate to User A's event edit page
2. Change the title to "Admin Edited"
3. Click Save

**Expected Result:**
- The admin sees a fully editable form (not read-only)
- Save and Delete buttons are visible
- The title change is saved successfully
- The admin is redirected back to the calendar

**Pass/Fail:** [ ]

---

## Summary Checklist

| ID | Category | Description | Pass/Fail |
|----|----------|-------------|-----------|
| QA-001 | Timezone | Create event at 9 AM, verify display | [ ] |
| QA-002 | Timezone | Late night event on correct day | [ ] |
| QA-003 | Timezone | Gantt position at 2 PM | [ ] |
| QA-004 | Timezone | Week view correct day | [ ] |
| QA-005 | Timezone | Month view time display | [ ] |
| QA-006 | Timezone | "Now" line matches current time | [ ] |
| QA-007 | Timezone | Dashboard times match entered values | [ ] |
| QA-008 | Timezone | Edit form shows originally entered time | [ ] |
| QA-009 | Timezone | DST spring forward | [ ] |
| QA-010 | Timezone | Midnight edge case | [ ] |
| QA-011 | Feedback | Button visible when logged in | [ ] |
| QA-012 | Feedback | Button NOT visible when logged out | [ ] |
| QA-013 | Feedback | Modal opens on click | [ ] |
| QA-014 | Feedback | Submission success toast | [ ] |
| QA-015 | Feedback | Validation errors | [ ] |
| QA-016 | Feedback | Visible in Django admin | [ ] |
| QA-017 | Feedback | page_url auto-captured | [ ] |
| QA-018 | Feedback | All three categories work | [ ] |
| QA-019 | Feedback | Close without submitting | [ ] |
| QA-020 | Feedback | Submit from multiple pages | [ ] |
| QA-021 | Day View | Auto-scroll to current time | [ ] |
| QA-022 | Day View | Manual scroll left/right | [ ] |
| QA-023 | Day View | Sticky track labels | [ ] |
| QA-024 | Day View | Event blocks correct span | [ ] |
| QA-025 | Day View | "Now" line visible and positioned | [ ] |
| QA-026 | Day View | No events centers on current time | [ ] |
| QA-027 | Day View | Early events scroll to event area | [ ] |
| QA-028 | Day View | Responsive narrow window | [ ] |
| QA-029 | Day View | Axis hour markers full range | [ ] |
| QA-030 | Day View | Click event navigates correctly | [ ] |
| QA-031 | Visibility | Create event as User A | [ ] |
| QA-032 | Visibility | User B sees User A's event | [ ] |
| QA-033 | Visibility | User B read-only view (not redirect) | [ ] |
| QA-034 | Visibility | Form fields disabled | [ ] |
| QA-035 | Visibility | No Save/Delete buttons | [ ] |
| QA-036 | Visibility | Creator banner displayed | [ ] |
| QA-037 | Visibility | Cannot POST edits as non-owner | [ ] |
| QA-038 | Visibility | Creator name on month/week views | [ ] |
| QA-039 | Visibility | Creator name in Gantt tooltip | [ ] |
| QA-040 | Visibility | Admin can edit any event | [ ] |
