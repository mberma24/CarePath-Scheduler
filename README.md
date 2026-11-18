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

### Tests and lint

```bash
cd backend && pytest && ruff check .     # 204 tests
cd frontend && npm run lint
```

---

## Using the app

The page has three tabs.

- **K-passes**: pick a K-pass on the left; edit it on the right. Step changes save
  when you leave a field. Minutes snap to multiples of 15. Use ↑/↓ to reorder.
- **Schedules**: search for a patient or resource, pick a date, then click or drag over
  the timeline to block time. Click × on a block to delete it. Add patients and resources
  in the panel on the left.
- **Find earliest**: pick a K-pass, a patient, and a start date/time. The result is shown
  on a timeline with the resource used for every step. **Next slot** searches again from
  one slot later; **Schedule** books it.

---

## How scheduling works

All times are split into **15-minute slots** (`SLOT_MINUTES`, configurable).

1. **Search window.** From the requested start (never earlier than now) to the requested
   end. The default is now until midnight in the clinic's timezone. Both ends are
   rounded to slots. A K-pass longer than the window is rejected with a 422.
2. **Busy matrix.** One row of 0/1 per slot for the patient (row 0) and one row per
   resource the K-pass needs. A block marks every slot it touches as busy; partial
   overlaps round outward, so a 9:10–9:20 block makes 9:00–9:30 busy.
3. **"Any of type" steps.** Each type gets one combined row that is busy only when
   *every* resource of that type is busy.
4. **Sliding window.** The engine (`scheduling/engine.py`) slides the K-pass across the
   matrix, keeping a running count of busy cells, and returns the first offset where the
   patient is free for the whole K-pass and each step's row is free for that step. This
   is O(slots × steps) in the worst case and close to O(slots) in practice.
5. **Choosing a resource.** For an "any of type" step, the first resource of that type
   that is free for the *whole* step is used. The combined row can say "free" when the
   free doctor changes halfway through a step; in that case the search continues from the
   next slot until one resource covers the whole step.
6. **Booking** (`POST /schedule/book`) re-runs the search over a window exactly as long
   as the K-pass, so it succeeds only if that exact slot is still free. It then creates
   one block for the patient and one per step for that step's resource, **in a single
   transaction**. If the slot was taken in the meantime, it returns a 409.

### Rules the backend enforces

- A step's duration is a positive multiple of the slot size, up to 24 hours.
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
| 422   | Invalid input: bad duration, an empty K-pass, or a window shorter than the K-pass. |

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
  plain `fetch`, and plain CSS.

## Seed data

`python -m app.seed --reset` deletes everything and creates:

- 3 doctors, 2 NMTs, 2 scanners, and 8 patients.
- The K-passes Bone Scan, Follow-up (any doctor), and Cardiac Stress Test.
- About 300 blocks over today and the next 2 days, at any time of day: staff lunches,
  random staff and scanner blocks, and patient blocks. No owner gets overlapping blocks
  (tested in `tests/test_seed.py`).

The random parts use a fixed seed, so every reset gives the same pattern, relative to the
current day.

## Assumptions and limitations

- **No accounts.** Anyone using the app can edit everything (see Future work).
- **The browser's timezone.** The frontend shows and picks times in the browser's timezone.
  This matches the backend's clinic-day logic as long as the browser is in the clinic's
  timezone.
- **No migrations.** Tables are created on startup. After a schema change, run
  `python -m app.seed --reset` or delete `kpass_scheduler.db`.
- **SQLite.** Fine for a demo with one process. Booking does its check and insert in
  one transaction, but with many concurrent users you would want Postgres and row locking.
- **Default search** covers one day, which is configurable with `SCHEDULE_HORIZON_DAYS`.
  The UI searches from a chosen start until the end of that day.

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
