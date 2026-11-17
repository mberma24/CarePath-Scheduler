from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Block, KPass, Patient
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


def default_search_end(now: datetime) -> datetime:
    """Midnight (clinic time) at the end of the last horizon day; horizon 1 = end of today."""
    clinic_tz = ZoneInfo(settings.clinic_timezone)
    today = now.astimezone(clinic_tz).date()
    last_midnight = datetime.combine(
        today + timedelta(days=settings.schedule_horizon_days), time.min, tzinfo=clinic_tz
    )
    return last_midnight.astimezone(UTC)


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

    Searches [start, end), defaulting to now until the end of the horizon (today).
    Never searches the past. Returns None if nothing fits in the window.
    Raises ValueError if the K-pass has no steps or is longer than the window.
    """
    now = as_utc(now or datetime.now(UTC))

    # 1. Search window, aligned to slots, never before now.
    window_start = ceil_to_slot(max(as_utc(start), now) if start else now)
    window_end = floor_to_slot(as_utc(end) if end else default_search_end(now))

    # 2. Reject K-passes that can never fit.
    if not kpass.steps:
        raise ValueError("K-pass has no steps")
    total_minutes = sum(step.duration_minutes for step in kpass.steps)
    window_minutes = max(int((window_end - window_start).total_seconds() // 60), 0)
    if total_minutes > window_minutes:
        raise ValueError(
            f"K-pass ({total_minutes} min) is longer than the search window ({window_minutes} min)"
        )
    num_slots = (window_end - window_start) // SLOT

    # 3. Give each distinct resource a row: patient = row 0, resources = 1, 2, ...
    resource_ids = list(
        dict.fromkeys(step.resource_id for step in kpass.steps if step.resource_id is not None)
    )
    row_of = {resource_id: row for row, resource_id in enumerate(resource_ids, start=1)}

    # 4. Load only the blocks that overlap the window, for this patient and these resources.
    blocks = db.scalars(
        select(Block).where(
            Block.end_time > window_start,
            Block.start_time < window_end,
            or_(Block.patient_id == patient.id, Block.resource_id.in_(resource_ids)),
        )
    ).all()

    # 5. Build the 0/1 matrix.
    patient_blocks = [b for b in blocks if b.patient_id == patient.id]
    schedule = [busy_row(patient_blocks, window_start, num_slots)]
    for resource_id in resource_ids:
        resource_blocks = [b for b in blocks if b.resource_id == resource_id]
        schedule.append(busy_row(resource_blocks, window_start, num_slots))

    # 6. Run the engine (minutes -> slots, resource_id -> row; rest steps stay None).
    engine_steps = [
        Step(
            duration_slots=step.duration_minutes // settings.slot_minutes,
            resource_row=row_of.get(step.resource_id)
            if step.resource_id is not None
            else step.resource_id,
        )
        for step in kpass.steps
    ]
    start_slot = find_earliest_start(engine_steps, schedule)
    if start_slot is None:
        return None

    # 7. Convert the slot back to real times, step by step.
    step_start = window_start + start_slot * SLOT
    scheduled_steps = []
    for step in kpass.steps:
        step_end = step_start + timedelta(minutes=step.duration_minutes)
        scheduled_steps.append(
            ScheduledStep(
                step_id=step.id,
                name=step.name,
                resource_id=step.resource_id,
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
