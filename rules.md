# Project Rules & Development Guidelines

> **IMPORTANT**: These guidelines are mandatory for all coding, branch management, migrations, and deployments within this project. You must strictly review and follow these rules before implementing any code updates, creating branches, executing merges, or applying migrations.

---

## 1. Branching Strategy & Coding Workflow

### 1.1 Never Code Directly on `develop`
- **Rule**: Direct commits or edits on the `develop` branch are strictly prohibited.
- **Workflow**:
  1. Ensure your local `develop` branch is up to date:
     ```bash
     git checkout develop
     git pull origin develop
     ```
  2. Always branch off `develop` into a dedicated working branch:
     - Feature branch: `feature/<feature-name>` (e.g., `feature/habit-reminders`)
     - Bugfix branch: `bugfix/<issue-name>` (e.g., `bugfix/streak-edge-case`)
     - Chore / Task branch: `task/<task-name>`
     ```bash
     git checkout -b feature/<feature-name>
     ```
  3. All code modifications, tests, and documentation updates must happen exclusively within this dedicated branch.

### 1.2 Merging into `develop` Requires Approval
- **Rule**: Never merge feature/fix branches into `develop` automatically or without explicit authorization.
- **Procedure**:
  - Verify that all unit and integration tests pass locally.
  - Present the code changes and test results to the user for review.
  - **Only when explicit user approval is granted**, proceed with merging the feature branch into `develop`.

---

## 2. Release & Environment Promotion (`stage` & `main`)

### 2.1 Explicit User Approval Required for `stage` and `main`
- **Rule**: Promotion of code to `stage` or `main` must NEVER occur autonomously.
- **Promotion Pipeline**:
  $$\text{Feature Branch} \xrightarrow[\text{Approval}]{\text{User}} \text{develop} \xrightarrow[\text{Approval}]{\text{User}} \text{stage} \xrightarrow[\text{Approval}]{\text{User}} \text{main}$$
- **Requirements**:
  - **Stage Branch (`stage`)**: Only merge `develop` into `stage` after receiving direct confirmation from the user.
  - **Main / Production Branch (`main`)**: Only merge `stage` (or `develop`) into `main` after receiving direct confirmation from the user.
  - No automated scripts, CI actions, or agent actions should trigger merges into `stage` or `main` without manual confirmation.

---

## 3. Database & Data Integrity Protection

### 3.1 Strict Prohibition on Clearing Database Records
- **Rule**: **NEVER clear, wipe, truncate, drop, or flush database data** when:
  - Merging branches
  - Syncing branches with latest code
  - Applying schema updates or migrations
  - Switching branches
- **Philosophy**: **Data is precious.** Existing user records, tenant profiles, habits, logs, and completion history must remain intact across all environments and development cycles.

### 3.2 Prohibited Commands (Unless Explicitly Commanded)
The following actions and commands are strictly forbidden unless the user provides an unambiguous, written instruction to clear or reset data:
- `python manage.py flush`
- `python manage.py reset_db`
- `DROP DATABASE ...`, `DROP TABLE ...`, `TRUNCATE ...`
- Custom management commands or seed scripts that purge existing rows (`.delete()`, `DELETE FROM`)
- Deleting PostgreSQL volumes, data directories, or SQLite database files

### 3.3 Safe Migration & Syncing Protocol
When syncing code and applying updates:
1. **Additive Schema Changes**: Always design database migrations to be additive and non-destructive.
2. **Standard Migration**: Run non-destructive Django migrations only:
   ```bash
   python manage.py migrate
   ```
3. **Backup Before High-Risk Operations**: If a complex data migration is unavoidable, prompt and ensure a backup exists prior to execution.
4. **Exception Handling**: If a test or scenario genuinely requires a clean state, use isolated test databases (e.g., standard Django test runner / `pytest-django` which spins up a temporary test database), never the actual working database.

---

## 4. Pre-Task Execution Checklist

Before writing any code or executing git/database operations, verify:

- [ ] Am I currently on a dedicated feature/bugfix branch? (Not `develop`, not `stage`, not `main`)
- [ ] If I need to merge into `develop`, has the user explicitly approved the merge?
- [ ] If I need to merge into `stage` or `main`, has the user explicitly approved the merge?
- [ ] Will any planned command or script affect existing database records? (Ensure zero data loss)
