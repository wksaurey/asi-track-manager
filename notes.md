# Use Cases
- As a user, I can see all available tracks and vehicles.
- As a user, I can see if a track or a vehicle has been reserved for a specific date and time.
- As a user, I can reserve a track or a vehicle for a specific date and time.
- As a user, I can modify reservation data: track, vehicle, time.
- As a user, I can't reserve a track or a vehicle for a time that they are already reserved for.
- As an admin, I can add a vehicle or track.
- As an admin, I can see all reservations made.
- As an admin, I can cancel a reservation.
- As an admin, I can modify a reservation.

# Core Entities
- Track
    * A designated testing area on ASI Mendon Campus
- Vehicle
    * An autonomous (or soon to be) vehicle
- Reservation
    * A time slot made by a user to reserve a Track and/or Vehicle for future use
- User
    * An ASI Employee that uses tracks or vehicles
- Admin
    * An ASI Employee that manages the scheduler

## Relationships
- A reservation belongs to one user (many users?)
- A reservation requires at least one vehicle or one track.
- A reservation may contain many vehicles and many tracks.
- A reservation requires a time slot of at least an hour.
- A user may have many reservations.

## Minimum Data Fields
- Track
    - Name
    - Description/Location
- Vehicle
    - Name
    - Description
- Reservation
    - Start Time
    - End Time
    - Track
    - Vehicle
    - User
    - created at
- User
    - Name
- Admin
    - Name

# Core Workflows

## Make an account
1. User selects create an account
2. User inputs name
3. User inputs password
4. System saves user data
5. User is logged in directly

## Make a Reservation
1. User chooses a time slot
2. User selects 0-many vehicles
3. User selects 0-many tracks
4. System checks for conflicts
5. System checks for at least 1 accepted vehicle or track
6. System saves reservation

# Initial App Structure
- reservations
- asi-assets
    - vehicles
    - tracks
- users
- calendar
    - https://github.com/huiwenhw/django-calendar/tree/master

# Good Enough (Growth ideas)
- No approvals required yet
- No notes yet
- No Jira integration yet
- No recurring reservations
- Try for calendar UI, but if it doesn't work that's fine

# Out of Scope
- User permissions beyond login
- Vehicle maintenance
- Notification system (teams or outlook integration)
- Calendar syncing
- No Jira linking (yet)

# UI Wireframe

## Pages
- Login/Signup
- Login
- Signup
- Home
- Make a Reservation
- Reservation
- Assets
- Vehicle
- Track
- Calender*
    - Schedule View
    - Month View
    - Week View
    - Day View

# Notes
- Should I include the workbays as tracks?
- Should a reservation be able to be used by multiple users?

## Implementation Notes

These notes bridge the original spec above to the actual implementation.

- **Unified Asset model:** Assets are implemented as a single `Asset` model with an `asset_type` field (choices: TRACK, VEHICLE, OPERATOR) rather than separate Track and Vehicle models as originally planned.
- **App structure:** Two apps were implemented — `cal` (calendar UI, events, assets, approval workflow) and `users` (auth/registration) — rather than the originally planned `reservations`, `asi-assets`, and `calendar` split.
- **Operators as first-class assets:** Operators (human test operators) were added as a first-class asset type alongside vehicles and tracks.
- **Admin approval workflow:** User-created events default to pending and require admin approval before they are confirmed. Admin-created events are auto-approved. This replaces the original "no approvals required yet" stance.
- **Events vs. Reservations:** The domain model uses "Event" rather than "Reservation" throughout the codebase, reflecting the calendar-centric UI.
- **Subtrack support:** Tracks can have a parent track, enabling hierarchical track structures (e.g., "North Main" as a parent with "Left Lane" and "Right Lane" as subtracks).
- **Conflict detection:** Booking a parent track conflicts with all its subtracks (and vice versa); booking a subtrack conflicts with its parent and any other booking of itself.
