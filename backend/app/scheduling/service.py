from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Block, KPass, KPassStep, Patient, Resource
from app.scheduling.engine import Step, find_earliest_start

SLOT = timedelta(minutes=settings.slot_minutes)


def as_utc(dt: datetime) -> datetime:
    """Treat naive datetimes as UTC (SQLite drops the offset); convert aware ones to UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def floor_to_slot(dt: datetime) -> datetime:
    """Round down to a slot boundary, e.g. 9:07 -> 9:00 (with 15-minute slots)."""
    dt = as_utc(dt)
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + ((dt - midnight) // SLOT) * SLOT


def ceil_to_slot(dt: datetime) -> datetime:
    """Round up to a slot boundary, e.g. 9:07 -> 9:15. Already-aligned times stay the same."""
    floored = floor_to_slot(dt)
    return floored if floored == as_utc(dt) else floored + SLOT


def busy_row(blocks: list[Block], origin: datetime, num_slots: int) -> list[int]:
    """
    Build one 0/1 schedule row of num_slots slots starting at origin (slot-aligned, UTC).

    A slot is busy (1) if any block overlaps it at all, so partial overlaps round outward:
    a 9:10-9:20 block marks the 9:00-9:15 and 9:15-9:30 slots busy.
    Blocks outside the window are clipped away.
    """
    row = [0] * num_slots
    for block in blocks:
        first = (floor_to_slot(block.start_time) - origin) // SLOT
        end = (ceil_to_slot(block.end_time) - origin) // SLOT  # exclusive
        for i in range(max(first, 0), min(end, num_slots)):
            row[i] = 1
    return row


@dataclass(frozen=True)
class ScheduledStep:
    step_id: int
    name: str
    resource_id: int | None
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class ScheduleResult:
    start_time: datetime
    end_time: datetime
    steps: list[ScheduledStep]


def clinic_tz() -> ZoneInfo:
    return ZoneInfo(settings.clinic_timezone)


def default_search_end(start: datetime) -> datetime:
    """Midnight (clinic time) ending the horizon, counted from the start's day.

    Horizon 1 = end of the start's day; horizon 7 = end of the 7th day.
    """
    first_day = as_utc(start).astimezone(clinic_tz()).date()
    last_midnight = datetime.combine(
        first_day + timedelta(days=settings.schedule_horizon_days), time.min, tzinfo=clinic_tz()
    )
    return last_midnight.astimezone(UTC)


def clinic_day_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """The open hours of each clinic day, clipped to [start, end) and aligned to slots."""
    windows = []
    day = start.astimezone(clinic_tz()).date()
    last_day = end.astimezone(clinic_tz()).date()
    while day <= last_day:
        opens = datetime.combine(day, time(settings.clinic_open_hour), tzinfo=clinic_tz())
        closes = datetime.combine(day, time(settings.clinic_close_hour), tzinfo=clinic_tz())
        window_start = ceil_to_slot(max(start, opens.astimezone(UTC)))
        window_end = floor_to_slot(min(end, closes.astimezone(UTC)))
        if window_end > window_start:
            windows.append((window_start, window_end))
        day += timedelta(days=1)
    return windows


def find_earliest_schedule(
    db: Session,
    kpass: KPass,
    patient: Patient,
    start: datetime | None = None,
    end: datetime | None = None,
    now: datetime | None = None,
) -> ScheduleResult | None:
    """
    Find the earliest time the patient can do every K-pass step back-to-back.

    Searches [start, end), defaulting to now until the end of the horizon
    (SCHEDULE_HORIZON_DAYS, counted from the start's day). Never searches the past.
    Appointments stay inside clinic hours, so the search runs one clinic day at a time
    and returns the first day that fits. Returns None if no day has a slot.
    Raises ValueError if the K-pass has no steps or can't fit in any day of the window.
    """
    now = as_utc(now or datetime.now(UTC))

    # 1. Search window, aligned to slots, never before now.
    search_start = ceil_to_slot(max(as_utc(start), now) if start else now)
    search_end = floor_to_slot(as_utc(end) if end else default_search_end(search_start))

    # 2. Reject K-passes that can never fit.
    if not kpass.steps:
        raise ValueError("K-pass has no steps")
    total_minutes = sum(step.duration_minutes for step in kpass.steps)
    day_minutes = (settings.clinic_close_hour - settings.clinic_open_hour) * 60
    if total_minutes > day_minutes:
        raise ValueError(
            f"K-pass ({total_minutes} min) is longer than a clinic day ({day_minutes} min)"
        )

    # 3. One search per clinic day; days with too little time left are skipped.
    total = timedelta(minutes=total_minutes)
    windows = [(s, e) for s, e in clinic_day_windows(search_start, search_end) if e - s >= total]
    if not windows:
        longest = max(
            (
                int((e - s).total_seconds() // 60)
                for s, e in clinic_day_windows(search_start, search_end)
            ),
            default=0,
        )
        raise ValueError(
            f"K-pass ({total_minutes} min) is longer than the search window ({longest} min)"
        )
    for window_start, window_end in windows:
        result = search_window(db, kpass, patient, window_start, window_end)
        if result is not None:
            return result
    return None


def search_window(
    db: Session, kpass: KPass, patient: Patient, window_start: datetime, window_end: datetime
) -> ScheduleResult | None:
    """Earliest slot inside one slot-aligned window (one clinic day), or None."""
    num_slots = (window_end - window_start) // SLOT

    # a. Rows: patient = row 0, then one row per specific resource, then one per type pool.
    resource_ids = list(
        dict.fromkeys(step.resource_id for step in kpass.steps if step.resource_id is not None)
    )
    resource_types = list(
        dict.fromkeys(step.resource_type for step in kpass.steps if step.resource_type is not None)
    )
    pool = {
        resource_type: list(
            db.scalars(
                select(Resource.id).where(Resource.type == resource_type).order_by(Resource.id)
            )
        )
        for resource_type in resource_types
    }
    row_of = {resource_id: row for row, resource_id in enumerate(resource_ids, start=1)}
    row_of_type = {
        resource_type: row
        for row, resource_type in enumerate(resource_types, start=len(resource_ids) + 1)
    }
    all_resource_ids = list(dict.fromkeys(resource_ids + [r for ids in pool.values() for r in ids]))

    # b. Load only the blocks that overlap the window, for this patient and these resources.
    blocks = db.scalars(
        select(Block).where(
            Block.end_time > window_start,
            Block.start_time < window_end,
            or_(Block.patient_id == patient.id, Block.resource_id.in_(all_resource_ids)),
        )
    ).all()

    # c. Build the 0/1 matrix. A pool slot is busy only if every resource of that type is busy.
    patient_blocks = [b for b in blocks if b.patient_id == patient.id]
    busy = {
        resource_id: busy_row(
            [b for b in blocks if b.resource_id == resource_id], window_start, num_slots
        )
        for resource_id in all_resource_ids
    }
    schedule = [busy_row(patient_blocks, window_start, num_slots)]
    schedule += [busy[resource_id] for resource_id in resource_ids]
    for resource_type in resource_types:
        member_rows = [busy[resource_id] for resource_id in pool[resource_type]]
        if member_rows:
            schedule.append([min(cells) for cells in zip(*member_rows, strict=True)])
        else:
            schedule.append([1] * num_slots)  # no resources of this type left: never free

    # d. Run the engine (minutes -> slots; rest steps stay None).
    def resource_row(step: KPassStep) -> int | None:
        if step.resource_id is not None:
            return row_of[step.resource_id]
        if step.resource_type is not None:
            return row_of_type[step.resource_type]
        return None

    engine_steps = [
        Step(
            duration_slots=step.duration_minutes // settings.slot_minutes,
            resource_row=resource_row(step),
        )
        for step in kpass.steps
    ]

    def assign_pools(start_slot: int) -> list[int | None] | None:
        """Resource for each step, picking one free resource for each pool step's whole interval."""
        assigned: list[int | None] = []
        slot = start_slot
        for step, engine_step in zip(kpass.steps, engine_steps, strict=True):
            end_slot = slot + engine_step.duration_slots
            if step.resource_type is None:
                assigned.append(step.resource_id)
            else:
                free = [r for r in pool[step.resource_type] if not any(busy[r][slot:end_slot])]
                if not free:
                    return None  # each slot has a free resource, but no single one covers the step
                assigned.append(free[0])
            slot = end_slot
        return assigned

    # The pool rows can say "free" when the free resource changes mid-step, so check the
    # assignment and, if it fails, search again from the next slot.
    offset = 0
    while True:
        found = find_earliest_start(engine_steps, [row[offset:] for row in schedule])
        if found is None:
            return None
        start_slot = offset + found
        assigned = assign_pools(start_slot)
        if assigned is not None:
            break
        offset = start_slot + 1

    # e. Convert the slot back to real times, step by step.
    step_start = window_start + start_slot * SLOT
    scheduled_steps = []
    for step, resource_id in zip(kpass.steps, assigned, strict=True):
        step_end = step_start + timedelta(minutes=step.duration_minutes)
        scheduled_steps.append(
            ScheduledStep(
                step_id=step.id,
                name=step.name,
                resource_id=resource_id,
                start_time=step_start,
                end_time=step_end,
            )
        )
        step_start = step_end

    return ScheduleResult(
        start_time=scheduled_steps[0].start_time,
        end_time=scheduled_steps[-1].end_time,
        steps=scheduled_steps,
    )


def book_schedule(
    db: Session,
    kpass: KPass,
    patient: Patient,
    start: datetime,
    now: datetime | None = None,
) -> ScheduleResult | None:
    """
    Book the K-pass starting exactly at `start` by blocking the patient and each step's resource.

    Re-checks that the slot is still free (searching a window exactly as long as the K-pass)
    and creates every block in one commit. Returns None if the slot is no longer free.
    Raises ValueError like find_earliest_schedule (e.g. the K-pass has no steps or start passed).
    """
    start = as_utc(start)
    if start != floor_to_slot(start):
        raise ValueError("start must be on a slot boundary")
    total = timedelta(minutes=sum(step.duration_minutes for step in kpass.steps))
    result = find_earliest_schedule(db, kpass, patient, start=start, end=start + total, now=now)
    if result is None or result.start_time != start:
        return None  # never book a different time than the one requested

    reason = f"{kpass.name} - {patient.name}"[:200]
    db.add(
        Block(
            patient_id=patient.id,
            start_time=result.start_time,
            end_time=result.end_time,
            reason=reason,
        )
    )
    for step in result.steps:
        if step.resource_id is not None:
            db.add(
                Block(
                    resource_id=step.resource_id,
                    start_time=step.start_time,
                    end_time=step.end_time,
                    reason=reason,
                )
            )
    db.commit()
    return result
