"""Fill the local database with demo data.

Usage (from backend/):
    python -m app.seed          # seed an empty database
    python -m app.seed --reset  # delete everything, then seed
"""

import argparse
import random
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Base, Block, KPass, KPassStep, Patient, Resource
from app.db.session import SessionLocal, engine


def seed(db: Session, now: datetime) -> None:
    rng = random.Random(42)  # fixed seed: same pattern every reset, relative to today

    # Resources
    dr_lee = Resource(name="Dr. Lee", type="doctor")
    dr_kim = Resource(name="Dr. Kim", type="doctor")
    dr_patel = Resource(name="Dr. Patel", type="doctor")
    nmt_sam = Resource(name="Sam Rivera", type="nmt")
    nmt_jo = Resource(name="Jo Chen", type="nmt")
    scanner_1 = Resource(name="Scanner 1", type="scanner")
    scanner_2 = Resource(name="Scanner 2", type="scanner")
    staff = [dr_lee, dr_kim, dr_patel, nmt_sam, nmt_jo]
    resources = [*staff, scanner_1, scanner_2]

    # Patients
    patients = [
        Patient(name=name)
        for name in [
            "Ann Patel",
            "Ben Okafor",
            "Cara Jensen",
            "Diego Ramos",
            "Emma Larsen",
            "Farah Haddad",
            "George Ito",
            "Hana Novak",
        ]
    ]

    # K-passes (the interview example, a short one, and one with a type-only chain)
    bone_scan = KPass(
        name="Bone Scan",
        steps=[
            KPassStep(position=0, name="Doctor consult", duration_minutes=45, resource=dr_lee),
            KPassStep(position=1, name="Rest", duration_minutes=30),
            KPassStep(position=2, name="Rest", duration_minutes=30),
            KPassStep(position=3, name="NMT injection", duration_minutes=30, resource_type="nmt"),
            KPassStep(position=4, name="Scan", duration_minutes=30, resource_type="scanner"),
        ],
    )
    follow_up = KPass(
        name="Follow-up",
        steps=[
            KPassStep(position=0, name="Doctor review", duration_minutes=30, resource_type="doctor")
        ],
    )
    cardiac = KPass(
        name="Cardiac Stress Test",
        steps=[
            KPassStep(position=0, name="Injection", duration_minutes=15, resource_type="nmt"),
            KPassStep(position=1, name="Rest", duration_minutes=45),
            KPassStep(position=2, name="Rest scan", duration_minutes=30, resource_type="scanner"),
            KPassStep(position=3, name="Stress test", duration_minutes=30, resource_type="doctor"),
            KPassStep(position=4, name="Stress scan", duration_minutes=30, resource_type="scanner"),
        ],
    )

    # Blocks for today and the next 2 days, within clinic hours (clinic time).
    clinic_tz = ZoneInfo(settings.clinic_timezone)
    today = now.astimezone(clinic_tz).date()

    def at(day: int, minute: int) -> datetime:
        midnight = datetime.combine(today + timedelta(days=day), time.min, tzinfo=clinic_tz)
        return midnight + timedelta(minutes=minute)

    blocks: list[Block] = []
    taken: dict[int, list[tuple[datetime, datetime]]] = {}  # owner -> its block times

    def add_block(owner: Patient | Resource, start: datetime, end: datetime, reason: str) -> bool:
        """Add a block unless it overlaps one the owner already has (back-to-back is fine)."""
        times = taken.setdefault(id(owner), [])
        if any(start < other_end and other_start < end for other_start, other_end in times):
            return False
        times.append((start, end))
        key = "patient" if isinstance(owner, Patient) else "resource"
        blocks.append(Block(start_time=start, end_time=end, reason=reason, **{key: owner}))
        return True

    def add_random_blocks(owner, count: int, lengths: list[int], reasons: list[str], day: int):
        added = tries = 0
        while added < count and tries < 50:  # give up on a crowded day instead of looping
            tries += 1
            length = rng.choice(lengths)
            opens, closes = settings.clinic_open_hour * 60, settings.clinic_close_hour * 60
            start = rng.randrange(opens, closes - length + 1, 15)
            if add_block(owner, at(day, start), at(day, start + length), rng.choice(reasons)):
                added += 1

    staff_reasons = ["Patient visit", "Meeting", "Rounds", "Paperwork", "On call", "Training"]
    scanner_reasons = ["Booked scan", "Calibration", "Maintenance", "Cleaning"]
    patient_reasons = ["Work", "School pickup", "Other appointment", "Travel", "Unavailable"]

    for day in range(3):
        for person in staff:  # staggered lunch breaks, placed first
            start = 12 * 60 + rng.choice([-30, 0, 30])
            add_block(person, at(day, start), at(day, start + 45), "Lunch")
        for resource in resources:
            reasons = scanner_reasons if resource.type == "scanner" else staff_reasons
            add_random_blocks(resource, rng.randint(8, 12), [30, 45, 60, 90, 120], reasons, day)
        for patient in patients:
            add_random_blocks(patient, rng.randint(3, 5), [30, 60, 90, 120], patient_reasons, day)

    db.add_all([*resources, *patients, bone_scan, follow_up, cardiac, *blocks])
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill the local database with demo data.")
    parser.add_argument("--reset", action="store_true", help="delete all data before seeding")
    args = parser.parse_args()

    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        if db.scalar(select(Patient.id).limit(1)) is not None:
            print("Database already has data. Run with --reset to start over.")
            return
        seed(db, datetime.now(UTC))

    print("Seeded demo data.")


if __name__ == "__main__":
    main()
