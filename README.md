# HabitPulse — Multi-Tenant Habit Tracking Application

HabitPulse is a robust, multi-tenant habit tracking web application built with **Python 3.9+**, **Django 4.2 LTS**, and **PostgreSQL 16**. It is designed with a secure, extensible foundation for personal workspaces today, ready to scale to multi-user organizations tomorrow.

---

## 1. Architecture Overview

### 1.1 Multi-Tenant Strategy
- **Shared Database, Shared Schema with Tenant Isolation**:
  - `Tenant`: Represents an isolated workspace entity with a unique slug and human-readable name.
  - `Membership`: Associates a `User` with a `Tenant`, assigning a role (`OWNER` or `MEMBER`) and status (`ACTIVE`). Enforces a database-level uniqueness constraint on `(user, tenant)`.
  - **Automatic Personal Workspace Provisioning**: Upon user registration, a personal workspace tenant (`"<username>'s Personal Workspace"`) and an `OWNER` membership are created in an atomic transaction.
  - **Tenant Scoping & Protection**:
    - All queries for `Habit` and `HabitCompletion` are strictly scoped to the authenticated user's active tenant (`request.tenant`).
    - Attempting to access another tenant's habit via URL manipulation returns a strict `404 Not Found` response to avoid disclosing record existence.
    - `HabitCompletion` enforces that its assigned `tenant` matches `habit.tenant`.

### 1.2 Core Entities & Data Model
- **User** (`accounts.User`): Custom user model inheriting from `AbstractUser` with unique email addresses. Supports logging in with either username or email via `EmailOrUsernameModelBackend`.
- **Tenant** (`tenants.Tenant`): Represents a workspace unit.
- **Membership** (`tenants.Membership`): Links users to tenants.
- **Habit** (`habits.Habit`): Stores habit parameters: name, description, category, frequency (`DAILY` or `WEEKDAYS`), selected weekdays (JSON list of ints 0–6), start date, and active status.
- **HabitCompletion** (`habits.HabitCompletion`): Stores daily completion records. Enforces a database-level unique constraint on `(habit, completion_date)`.

### 1.3 Scheduling & Analytics Services
- **Scheduling Rules**: Supports daily routines and specific days of the week (e.g., Mon/Wed/Fri). Dates prior to `start_date` and future dates are strictly excluded from completion eligibility.
- **Streak Calculation**:
  - **Current Streak**: Consecutive completed scheduled days up to today. If today is scheduled and completed, today counts. If today is scheduled but not yet completed, the streak from yesterday remains intact until the day concludes. If today is an unscheduled day, the streak is maintained from the most recent scheduled day. A missed scheduled day in the past breaks the streak.
  - **Longest Streak**: The maximum unbroken run of completed scheduled days across the habit's lifetime.
- **Completion Rate**: Calculated as `(completed eligible scheduled days / total eligible scheduled days) * 100`. If total eligible scheduled days is 0 (e.g., brand-new habit or rest days), returns `None` and displays an empty state instead of dividing by zero.
- **Monthly Calendar**: Generates a standard monthly grid with correct weekday offsets and visual state styling (`completed`, `missed`, `pending_today`, `unscheduled`, `future`), plus month-by-month navigation.

---

## 2. Project Directory Structure

```text
Habit/
├── .env.example                # Example environment variable template
├── .env                        # Local environment settings (git-ignored)
├── .gitignore                  # Git ignore rules
├── manage.py                   # Django management script
├── pytest.ini                  # Pytest configuration
├── requirements.txt            # Python dependencies
├── README.md                   # Setup documentation & verification checklist
├── config/                     # Project configuration
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py             # Settings (PostgreSQL, custom user, middleware)
│   ├── urls.py                 # Root URL routing
│   └── wsgi.py
├── accounts/                   # Authentication & user workflows
│   ├── backends.py             # Email or username auth backend
│   ├── forms.py                # Registration and login forms
│   ├── models.py               # Custom User model
│   ├── urls.py                 # /accounts/ URLs
│   └── views.py                # Register, login, logout views
├── tenants/                    # Multi-tenant workspace management
│   ├── context_processors.py   # Exposes active tenant to templates
│   ├── middleware.py           # Validates & attaches active tenant to request
│   ├── models.py               # Tenant and Membership models
│   ├── utils.py                # Workspace provisioning & helpers
│   └── admin.py
├── habits/                     # Habit core domain
│   ├── forms.py                # Habit creation and edit form
│   ├── models.py               # Habit and HabitCompletion models
│   ├── services.py             # Streak, rate, and calendar calculations
│   ├── urls.py                 # Habit CRUD, calendar, stats, complete/undo URLs
│   ├── views.py                # Habit views & daily tracking handlers
│   └── admin.py
├── dashboard/                  # Dashboard presentation
│   ├── urls.py                 # Dashboard root URL
│   └── views.py                # Habit cards aggregation & today's status
├── templates/                  # Server-rendered HTML templates
│   ├── base.html               # Main layout shell
│   ├── includes/
│   │   ├── navbar.html         # Responsive header & workspace badge
│   │   └── messages.html       # Flash notification alerts
│   ├── accounts/
│   │   ├── login.html
│   │   └── register.html
│   ├── habits/
│   │   ├── onboarding.html     # Welcoming first-time user page
│   │   ├── habit_form.html     # Habit create/edit form
│   │   ├── habit_list.html     # Habit management & toggle view
│   │   ├── habit_calendar.html # Monthly grid & navigation
│   │   └── habit_stats.html    # Detailed analytics & progress bars
│   └── dashboard/
│       └── dashboard.html      # Main dashboard & celebratory banner
├── static/                     # CSS & vanilla JavaScript
│   ├── css/
│   │   └── style.css           # Modern design system & responsive layout
│   └── js/
│       └── app.js              # Minimal vanilla JS (weekday toggle, ajax completions)
└── tests/                      # Automated test suite (31 tests)
    ├── __init__.py
    ├── test_auth_and_tenants.py
    ├── test_tenant_isolation.py
    ├── test_habit_management.py
    ├── test_daily_tracking.py
    └── test_services_analytics.py
```

---

## 3. Technology Stack

- **Python**: 3.9+
- **Django**: 4.2 LTS
- **Database**: PostgreSQL 16
- **Database Driver**: `psycopg2-binary`
- **Frontend**: Semantic HTML5, Custom CSS3, Minimal Vanilla JavaScript
- **Test Runners**: Django `TestCase` and `pytest` / `pytest-django`

---

## 4. Setup and Execution Instructions

### Step 1: Clone and Navigate to the Repository
```powershell
cd c:\Users\SHRINATH\Alphabet_Shrinath\Habit
```

### Step 2: Create and Activate a Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Configure PostgreSQL
Ensure PostgreSQL is running. Create a dedicated database:
```sql
CREATE DATABASE habit_tracker;
```

### Step 5: Configure Environment Variables
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Update `.env` with your PostgreSQL database credentials:
```env
SECRET_KEY=your-secure-secret-key-for-development
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

DB_NAME=habit_tracker
DB_USER=your_postgres_user
DB_PASSWORD=your_postgres_password
DB_HOST=127.0.0.1
DB_PORT=5432

TIME_ZONE=UTC
```

### Step 6: Apply Database Migrations
```powershell
python manage.py migrate
```

### Step 7: Create a Superuser (Optional for Django Admin)
```powershell
python manage.py createsuperuser
```

### Step 8: Execute the Automated Test Suite
Run tests using Django's test runner:
```powershell
python manage.py test tests
```
Or run with pytest:
```powershell
pytest
```

### Step 9: Start the Development Server
```powershell
python manage.py runserver
```
Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your web browser.

---

## 5. Manual Verification Checklist

Follow this step-by-step checklist to manually test and verify every requirement in the browser:

### 1. User Registration & Personal Workspace Creation
- [ ] Visit `http://127.0.0.1:8000/`.
- [ ] You are presented with the clean **Login** page.
- [ ] Click **Sign up** to open the registration form.
- [ ] Register a new user: `testuser` / `testuser@example.com` / `Password123!`.
- [ ] Verify automatic redirection to the **First-Time Onboarding** page.
- [ ] Verify the header displays the workspace badge: `testuser's Personal Workspace`.

### 2. First-Time Onboarding Page
- [ ] Verify the onboarding page displays:
  - Headline: *"Build better habits, one day at a time."*
  - Friendly description of tracking routines and consistency.
  - Prominent **Create Your First Habit** button.
  - Quick inspiration list (Health, Fitness, Learning, etc.).

### 3. Habit Creation & Server Validation
- [ ] Click **Create Your First Habit**.
- [ ] Fill in:
  - Name: `Solve 2 DSA problems`
  - Category: `Learning`
  - Frequency: `Selected Days of the Week` (select Mon, Wed, Fri)
  - Start Date: Today's date
  - Active: Checked
- [ ] Submit the form.
- [ ] Verify success flash alert appears and you are redirected to the **Main Dashboard**.
- [ ] Create a second daily habit: `Drink 2L Water` (Category: `Health`, Frequency: `Every Day`).

### 4. Main Dashboard Experience
- [ ] Verify both habits are displayed in clear, rounded cards.
- [ ] Verify each card displays:
  - Habit name & category badge.
  - Current streak (`🔥 0 days`).
  - 7-day completion rate (`0.0%`).
  - Mark Complete button (for scheduled habits).
- [ ] Click **Mark Complete** on `Drink 2L Water`.
- [ ] Verify:
  - Today's status changes to `Done ✓`.
  - An **Undo** button appears.
  - Current streak increments to `🔥 1 days`.
  - 7-day completion rate updates to `100.0%`.
- [ ] Mark `Solve 2 DSA problems` as complete (if scheduled today).
- [ ] When all scheduled habits for today are completed, verify the **Celebration Banner** appears:
  *"Outstanding work! All scheduled habits completed today! Keep this momentum going tomorrow!"*
- [ ] Click **Undo** on one habit. Verify the celebration banner gracefully disappears and the habit returns to pending state.

### 5. Habit Monthly Calendar
- [ ] Click **Calendar** on `Drink 2L Water`.
- [ ] Verify the monthly grid displays:
  - Current month name and year header.
  - Correct Monday-through-Sunday column alignment.
  - Completed day highlighted in soft green with `✓`.
  - Today highlighted with active ring.
  - Unscheduled/rest days styled subtly.
  - Future days styled without being marked as missed.
  - Complete legend at the bottom.
- [ ] Test the **Prev** and **Next** navigation buttons to view previous and future months.

### 6. Habit Statistics Page
- [ ] Click **Stats** on `Drink 2L Water`.
- [ ] Verify key metrics:
  - Current Streak.
  - Longest Streak.
  - Total Completed Days.
  - Today's Status.
  - Last 7 Days consistency bar and completion percentage.
  - Last 30 Days consistency bar.
  - Lifetime adherence.
  - Empty states handled gracefully with no division-by-zero errors.

### 7. Habit Management & Deactivation
- [ ] Navigate to **Habits** in the top navigation bar.
- [ ] Click **Edit** on a habit. Update the description or schedule and save.
- [ ] Click **Deactivate** on a habit. Verify its status updates to `Inactive` and it is hidden from the daily focus dashboard.
- [ ] Click **Reactivate** to bring it back to the dashboard.

### 8. Strict Multi-Tenant Isolation
- [ ] Log out from `testuser`.
- [ ] Register a second user: `attacker` / `attacker@example.com` / `Password123!`.
- [ ] Note that `attacker` only sees their own blank onboarding page or personal habits.
- [ ] In the browser address bar, try accessing `testuser`'s habit directly:
  `http://127.0.0.1:8000/habits/1/edit/` or `/habits/1/calendar/` or `/habits/1/complete/`.
- [ ] Verify that a `404 Not Found` response is returned. `attacker` cannot view, edit, mark complete, or infer the existence of `testuser`'s habits.
