# ASI Track Manager

A Django-based scheduling and asset management system for ASI Mendon Campus. Reserve and track vehicles, heavy equipment tracks, and operators across time slots with a calendar interface and admin approval workflow.

## Features

- **Multi-view calendar** -- month, week, and day views with navigation and asset filtering
- **Asset management** -- track vehicles, testing tracks, and operators with color-coded display
- **Conflict detection** -- prevents double-booking assets during overlapping time slots
- **Approval workflow** -- user-created events require admin approval; admin events are auto-approved
- **Dark/light theme** -- toggle with localStorage persistence
- **Dual login** -- simple name-based user login or Django admin credentials for staff

## Tech Stack

- Python 3 / Django 5.2
- SQLite
- Bootstrap 4, FontAwesome 5, Flatpickr (via CDN)

## Setup

1. Create and activate a virtual environment:

    ```bash
    mkdir -p .venv/asi-track-manager
    python3 -m venv .venv/asi-track-manager
    . ./.venv/asi-track-manager/bin/activate
    ```

2. Install dependencies:

    ```bash
    python3 -m pip install -r requirements.txt
    ```

3. Run migrations:

    ```bash
    python manage.py migrate
    ```

4. Create an admin user:

    ```bash
    python manage.py createsuperuser
    ```

5. Start the development server:

    ```bash
    python manage.py runserver
    ```

## Development

- Activate the venv each time you start work
- After installing a new module, update requirements:

    ```bash
    python3 -m pip freeze > requirements.txt
    ```

- After changing models, create and apply migrations:

    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```
