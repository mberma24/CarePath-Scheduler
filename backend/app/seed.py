"""Fill the local database with demo data.

Usage (from backend/):
    python -m app.seed          # seed an empty database
    python -m app.seed --reset  # delete everything, then seed
"""

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Base, Block, KPass, KPassStep, Patient, Resource
from app.db.session import SessionLocal, engine
from app.scheduling.service import ceil_to_slot


def seed(db: Session, now: datetime) -> None:
    # Resources
    dr_lee = Resource(name="Dr. Lee", type="doctor")
    dr_kim = Resource(name="Dr. Kim", type="doctor")
    nmt_sam = Resource(name="Sam Rivera", type="nmt")
    scanner = Resource(name="Scanner 1", type="scanner")

    # Patients
    ann = Patient(name="Ann Patel")
    ben = Patient(name="Ben Okafor")
    cara = Patient(name="Cara Jensen")

    # K-passes (the interview example, plus a short one)
    bone_scan = KPass(
        name="Bone Scan",
        steps=[
            KPassStep(position=0, name="Doctor consult", duration_minutes=45, resource=dr_lee),
            KPassStep(position=1, name="Rest", duration_minutes=30),
            KPassStep(position=2, name="Rest", duration_minutes=30),
            KPassStep(position=3, name="NMT injection", duration_minutes=30, resource=nmt_sam),
            KPassStep(position=4, name="Scan", duration_minutes=30, resource=scanner),
        ],
    )
    follow_up = KPass(
        name="Follow-up",
        steps=[KPassStep(position=0, name="Doctor review", duration_minutes=30, resource=dr_kim)],
    )

    # Blocks, relative to now so the demo always looks realistic
    start = ceil_to_slot(now)

    def hours(h: float) -> datetime:
        return start + timedelta(hours=h)

    blocks = [
        Block(patient=ann, start_time=hours(0), end_time=hours(1), reason="Work call"),
        Block(resource=dr_lee, start_time=hours(1), end_time=hours(2), reason="Clinic"),
        Block(resource=scanner, start_time=hours(3), end_time=hours(4), reason="Maintenance"),
        Block(resource=dr_kim, start_time=hours(0), end_time=hours(0.5), reason="Meeting"),
        Block(patient=ben, start_time=hours(2), end_time=hours(5), reason="Unavailable"),
    ]

    db.add_all([dr_lee, dr_kim, nmt_sam, scanner, ann, ben, cara, bone_scan, follow_up, *blocks])
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
