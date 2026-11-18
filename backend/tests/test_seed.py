from datetime import UTC, datetime
from itertools import combinations
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.models import Block, KPass, Patient
from app.scheduling.service import find_earliest_schedule
from app.seed import seed


@pytest.mark.parametrize(
    "now",
    [
        pytest.param(datetime(2026, 11, 18, 14, 7, tzinfo=UTC), id="weekday-afternoon"),
        pytest.param(datetime(2026, 11, 1, 4, 0, tzinfo=UTC), id="dst-end-night"),
        pytest.param(datetime(2026, 3, 8, 23, 59, tzinfo=UTC), id="dst-start-late"),
    ],
)
def test_seed_never_overlaps_blocks_for_one_owner(db, now):
    seed(db, now)

    by_owner: dict[tuple[int | None, int | None], list[Block]] = {}
    for block in db.scalars(select(Block)):
        by_owner.setdefault((block.patient_id, block.resource_id), []).append(block)

    assert sum(len(blocks) for blocks in by_owner.values()) > 100  # the seed is busy
    for owner, blocks in by_owner.items():
        for a, b in combinations(blocks, 2):
            overlap = a.start_time < b.end_time and b.start_time < a.end_time
            assert not overlap, (
                f"owner {owner}: {a.start_time}-{a.end_time} overlaps {b.start_time}-{b.end_time}"
            )


def test_seed_blocks_are_valid(db):
    seed(db, datetime(2026, 11, 18, 14, 7, tzinfo=UTC))

    for block in db.scalars(select(Block)):
        assert block.end_time > block.start_time
        assert (block.patient_id is None) != (block.resource_id is None)  # exactly one owner


def test_seed_has_one_patient_with_no_room_for_long_kpasses(db, monkeypatch):
    monkeypatch.setattr(settings, "schedule_horizon_days", 7)
    now = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)  # 7:00 in New York
    seed(db, now)
    hana = db.scalar(select(Patient).where(Patient.name == "Hana Novak"))
    ann = db.scalar(select(Patient).where(Patient.name == "Ann Patel"))
    kpasses = {k.name: k for k in db.scalars(select(KPass))}

    # No slot in the whole 7-day horizon for Hana's long K-passes...
    for name in ("Bone Scan", "Cardiac Stress Test"):
        assert find_earliest_schedule(db, kpasses[name], hana, now=now) is None
    # ...but other patients still get one.
    assert find_earliest_schedule(db, kpasses["Bone Scan"], ann, now=now) is not None


def test_seed_stores_clinic_hours_as_utc(db):
    # Every seeded block must fall inside 7:00-19:00 New York time once read back as UTC.
    seed(db, datetime(2026, 11, 18, 14, 7, tzinfo=UTC))
    clinic_tz = ZoneInfo(settings.clinic_timezone)
    for block in db.scalars(select(Block)):
        start = block.start_time.replace(tzinfo=UTC).astimezone(clinic_tz)
        end = block.end_time.replace(tzinfo=UTC).astimezone(clinic_tz)
        assert settings.clinic_open_hour <= start.hour
        assert (end.hour, end.minute) <= (settings.clinic_close_hour, 0)
