# KPass Scheduler

A small clinic scheduling app. A **K-pass** is an ordered list of steps a patient goes
through back-to-back, for example a bone scan:

| # | Step           | Minutes | Needs                |
|---|----------------|---------|----------------------|
| 1 | Doctor consult | 45      | Dr. Lee              |
| 2 | Rest           | 30      | nothing (rest step)  |
| 3 | Rest           | 30      | nothing (rest step)  |
| 4 | NMT injection  | 30      | any NMT              |
| 5 | Scan           | 30      | any scanner          |

The app lets you:

1. **Create and edit K-passes**: add, edit, reorder, and delete steps. A step needs a
   specific resource, *any* resource of a type (e.g. any doctor), or nothing (rest).
2. **Edit schedules**: block out times when a patient or a resource (staff or equipment)
   is unavailable.
3. **Find the earliest schedule**: pick a K-pass, a patient, and a start time, and get the
   earliest time every step fits, then **book** it (or look at the next slot).

**Stack:** FastAPI, SQLAlchemy 2, Pydantic v2, and SQLite on the backend; React 19,
TypeScript, and Vite on the frontend.

---

## Running it

You need Python 3.11+ and Node 20.19+ (required by Vite).

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env               # optional; the defaults work
python -m app.seed --reset         # demo data (see "Seed data" below)
uvicorn app.main:app --reload      # http://localhost:8000, API docs at /docs
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env               # VITE_API_BASE_URL=http://localhost:8000
npm run dev                        # http://localhost:5173
```

### Settings

Backend settings come from `backend/.env` (or environment variables):

| Setting                 | Default              | Meaning                                       |
|-------------------------|----------------------|-----------------------------------------------|
| `SLOT_MINUTES`          | `15`                 | Scheduling granularity                        |
| `SCHEDULE_HORIZON_DAYS` | `7`                  | How many calendar days a search covers        |
| `CLINIC_OPEN_HOUR`      | `7`                  | Earliest appointment time (clinic time)       |
| `CLINIC_CLOSE_HOUR`     | `19`                 | Appointments must finish by this hour         |
| `CLINIC_TIMEZONE`       | `America/New_York`   | Timezone for "today" and clinic hours         |

The frontend reads these from `GET /config`.

### Tests and lint

```bash
cd backend && pytest && ruff check .     # 221 tests
cd frontend && npm run lint
```

---

## Using the app

The page has three tabs.

- **K-passes**: pick a K-pass on the left; edit it on the right. Step changes save
  when you leave a field. Minutes snap to multiples of 15. Use ↑/↓ to reorder.
- **Schedules**: search for a patient or resource, pick a date, then click or drag over
  the timeline (clinic hours only) to block time. A drag stops at an existing block, so blocks never overlap.
  Click × on a block to delete it. Add patients and resources in the panel on the left.
- **Find earliest**: pick a K-pass, a patient, and a start date/time. It searches that day
  and the following days of the horizon (7 by default), within clinic hours. The result
  shows the day and a timeline with the resource used for every step. **Next slot**
  searches again from one slot later (same end); **Schedule** books it.

Clicking the selected item in a list again unselects it.

### Viewing as (demo roles)

The **Viewing as** picker in the top right switches between roles. It is searchable and
scrolls, so it works with many people.

| Role                             | Tabs                                | What they can do                                  |
|----------------------------------|-------------------------------------|---------------------------------------------------|
| **Admin** (default)              | K-passes, Schedules, Find earliest  | Everything                                        |
| **Patient** (e.g. Ann Patel)     | Schedules, Find earliest            | See and block only their own time; find and book times only for themselves |
| **Staff / equipment** (e.g. Dr. Lee) | K-passes, Schedules, Find earliest | Edit only their own time; create and edit K-passes; find times for any patient |

This is a **UI demo only**. The API does not check roles (see
[Assumptions and limitations](#assumptions-and-limitations) and
[Future work](#future-work)).

---

## How scheduling works

All times are split into **15-minute slots** (`SLOT_MINUTES`, configurable).

1. **Search window.** From the requested start (never earlier than now) to the requested
   end. The default end covers `SCHEDULE_HORIZON_DAYS` **calendar days** in the clinic's
   timezone, counting the start's day: a 7-day horizon from Nov 18, 6 PM searches Nov 18–24.
   Both ends are rounded to slots.
2. **Clinic hours, one day at a time.** Appointments must start and finish between
   `CLINIC_OPEN_HOUR` and `CLINIC_CLOSE_HOUR` (7 AM–7 PM by default). The service runs the
   search below once per clinic day, in order, and returns the first day with a slot. Each
   day's opening and closing times are built in the clinic's timezone and then converted
   to UTC, so daylight saving changes are handled. Days with too little time left are
   skipped; if no day has room, the answer is `found: false` (for example, pressing
   **Next slot** at the end of the range). Only a K-pass longer than a clinic day is a 422. `engine.py` is unchanged; the day loop lives in `service.py`.
3. **Busy matrix.** One row of 0/1 per slot for the patient (row 0) and one row per
   resource the K-pass needs. A block marks every slot it touches as busy; partial
   overlaps round outward, so a 9:10–9:20 block makes 9:00–9:30 busy.
4. **"Any of type" steps.** Each type gets one combined row that is busy only when
   *every* resource of that type is busy.
5. **Sliding window.** The engine (`scheduling/engine.py`) slides the K-pass across the
   matrix, keeping a running count of busy cells, and returns the first offset where the
   patient is free for the whole K-pass and each step's row is free for that step. This
   is O(slots × steps) in the worst case and close to O(slots) in practice.
6. **Choosing a resource.** For an "any of type" step, the first resource of that type
   that is free for the *whole* step is used. The combined row can say "free" when the
   free doctor changes halfway through a step; in that case the search continues from the
   next slot until one resource covers the whole step.
7. **Booking** (`POST /schedule/book`) re-runs the search over a window exactly as long
   as the K-pass, so it succeeds only if that exact slot is still free and inside clinic
   hours. It also checks explicitly that the result starts at the requested time, so a
   booking can never land on a different time than the one the user saw. It then creates
   one block for the patient and one per step for that step's resource, **in a single
   transaction**. If the slot was taken in the meantime, it returns a 409.

### Rules the backend enforces

- A step's duration is a positive multiple of the slot size, and a whole K-pass can be at
  most one clinic day long (12 hours by default); adding or editing a step past that is a 422.
- A step that needs "any" of a type with no resources left gives a 422 explaining why,
  instead of a silent "no slot".
- Booking a start time that has already passed is a 422 ("That time has already passed").
- A step sets at most one of `resource_id` / `resource_type` (both empty means a rest step).
- One owner (patient or resource) can't have overlapping blocks; back-to-back is fine.
  Two different owners can be busy at the same time.
- Every block has exactly one owner, and its end is after its start.
- A resource used by a K-pass step can't be deleted (409).

### Status codes

| Code  | Meaning                                                                  |
|-------|--------------------------------------------------------------------------|
| 200   | OK. `POST /schedule` with no free slot returns `found: false`, not an error. |
| 201   | Created (including a booking).                                           |
| 404   | The K-pass, step, patient, resource, or block doesn't exist.             |
| 409   | Conflicts: an overlapping block, a slot that was just taken, or a resource still in use. |
| 422   | Invalid input: bad duration, an empty K-pass, a K-pass longer than a clinic day, a type with no resources, or booking a time that has passed. |

---

## API

Interactive docs are at `http://localhost:8000/docs`.

| Method                | Path                                  | Purpose                                         |
|-----------------------|---------------------------------------|-------------------------------------------------|
| GET/POST              | `/patients`                           | List / create patients                          |
| GET/PUT/DELETE        | `/patients/{id}`                      | Read / rename / delete a patient                |
| GET/POST              | `/resources`                          | List (optionally `?type=`) / create resources   |
| GET/PUT/DELETE        | `/resources/{id}`                     | Read / update / delete a resource               |
| GET/POST              | `/kpasses`                            | List / create K-passes (with steps and `total_minutes`) |
| GET/PUT/DELETE        | `/kpasses/{id}`                       | Read / rename / delete a K-pass                 |
| POST                  | `/kpasses/{id}/steps`                 | Add a step (optionally at a `position`)         |
| PUT                   | `/kpasses/{id}/steps`                 | Reorder: body `{"step_ids": [...]}`             |
| PUT/DELETE            | `/kpasses/{id}/steps/{step_id}`       | Edit / delete a step                            |
| GET/POST              | `/blocks`                             | List (filter by owner and `start`/`end`) / create blocks |
| GET/PUT/DELETE        | `/blocks/{id}`                        | Read / move / delete a block                    |
| POST                  | `/schedule`                           | Find the earliest slot                          |
| POST                  | `/schedule/book`                      | Book a slot found by `/schedule`                |
| GET                   | `/config`                             | Slot size, search horizon, and clinic hours     |
| GET                   | `/health`                             | Health check                                    |

---

## Design decisions

- **Separate step endpoints.** Steps are added, edited, reordered, and deleted one at a
  time, so each change is small and atomic, and the UI saves each change right away.
  Positions are kept as 0..n-1 under a unique `(kpass_id, position)` constraint; renumbering
  moves steps to temporary negative positions first, so it never breaks the constraint.
- **The engine is pure.** `engine.py` knows only about slots and 0/1 rows, which makes it
  easy to test. `service.py` turns database rows into that matrix and back into times.
- **UTC everywhere.** Times are stored as UTC. SQLite drops the timezone, so it is put back
  when reading. The API needs times with an offset. "Today" is calculated in the clinic's
  timezone (`CLINIC_TIMEZONE`, default `America/New_York`).
- **Bookings are just blocks.** A booked appointment is a set of blocks with a reason like
  "Bone Scan - Ann Patel", so the scheduler treats it like any other busy time.
- **A simple frontend.** No router or state library: one page, three tabs, `useState`,
  plain `fetch`, and plain CSS. All API calls are in `api.ts`. Two small shared
  components: `Timeline` (the day view used by Schedules and Find earliest) and
  `RolePicker` (the searchable "Viewing as" picker).

## Seed data

`python -m app.seed --reset` deletes everything and creates:

- 3 doctors, 2 NMTs, 2 scanners, and 8 patients.
- The K-passes Bone Scan, Follow-up (any doctor), and Cardiac Stress Test.
- About 300 blocks over today and the next 2 days, within clinic hours: staff lunches,
  random staff and scanner blocks, and patient blocks. No owner gets overlapping blocks
  (tested in `tests/test_seed.py`).
- **A fully booked case:** Hana Novak only has two 1-hour gaps per day (10–11 AM and 3–4 PM)
  for the whole search horizon. Bone Scan and Cardiac Stress Test never fit for her, so
  Find earliest shows "No slot is available in the next 7 days", while Follow-up
  (30 min) can still be found.

The random parts use a fixed seed, so every reset gives the same pattern, relative to the
current day.

## Assumptions and limitations

- **No accounts.** The "Viewing as" switcher in the header shows the role model in the
  UI only: admins see everything, patients see their own schedule and can find times for
  themselves, and staff/equipment see their own schedule and can edit K-passes. The API
  does **not** enforce roles; anyone who calls it directly can do everything (see Future
  work for the real design).
- **The browser's timezone.** The frontend shows and picks times in the browser's timezone.
  This matches the backend's clinic-day logic as long as the browser is in the clinic's
  timezone.
- **No migrations.** Tables are created on startup. After a schema change, run
  `python -m app.seed --reset` or delete `kpass_scheduler.db`.
- **Concurrent bookings.** Booking checks the slot and inserts its blocks in one
  transaction, and the tests cover booking a slot that was *already* taken. They don't
  cover two requests booking the same slot at the *same moment*: both could pass the
  check before either inserts. SQLite makes this unlikely (it serializes writes), but a
  production system would use Postgres with row locks or an exclusion constraint on
  block times.
- **Stale searches.** If a K-pass is edited between Find and Schedule, booking re-checks
  against the *current* K-pass. A stricter version would reject the booking and ask the
  user to search again (for example by sending the expected end time).

## Future work

- **Accounts and roles.** Admins can edit every schedule and K-pass. Patients and staff
  sign in to see their own schedule and block only their own time. This would add a
  `users` table linked to a patient or resource, a login that issues a session or JWT,
  and a check on each endpoint (for example, a patient can only create blocks with their
  own `patient_id`).
- Search across a date range, and show free slots over several days.
- Cancel or move a booking as one unit (store bookings as their own table that owns the blocks).
- Database migrations with Alembic, and Postgres for production.
- Recurring blocks (for example, lunch every weekday).
