from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.db.models import Block, KPass, KPassStep, Patient, Resource
from app.scheduling.service import (
    ScheduleResult,
    ceil_to_slot,
    default_search_end,
    find_earliest_schedule,
    floor_to_slot,
)

NOW = datetime(2026, 11, 18, 14, 7, tzinfo=UTC)  # 9:07 in New York (UTC-5 in November)


def utc(hour, minute=0, day=18):
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def make_patient(db, name="Ann"):
    patient = Patient(name=name)
    db.add(patient)
    db.commit()
    return patient


def make_resource(db, name="Dr. Lee", type="doctor"):
    resource = Resource(name=name, type=type)
    db.add(resource)
    db.commit()
    return resource


def make_kpass(db, *steps):
    """Each step is a (duration_minutes, resource or None) pair, in order."""
    kpass = KPass(
        name="Test K-pass",
        steps=[
            KPassStep(position=i, name=f"Step {i}", duration_minutes=minutes, resource=resource)
            for i, (minutes, resource) in enumerate(steps)
        ],
    )
    db.add(kpass)
    db.commit()
    return kpass


def block(db, start, end, patient=None, resource=None):
    db.add(Block(start_time=start, end_time=end, patient=patient, resource=resource))
    db.commit()


def schedule(db, kpass, patient, **kwargs):
    kwargs.setdefault("now", NOW)
    return find_earliest_schedule(db, kpass, patient, **kwargs)


def found(db, kpass, patient, **kwargs) -> ScheduleResult:
    """Like schedule(), but the test expects a slot to be found."""
    result = schedule(db, kpass, patient, **kwargs)
    assert result is not None, "expected a schedule, got None"
    return result


# ---------- Basic scheduling ----------


def test_nothing_blocked_starts_at_next_slot_and_chains_steps(db):
    patient = make_patient(db)
    doctor = make_resource(db, "Dr. Lee", "doctor")
    nmt = make_resource(db, "Sam", "nmt")
    kpass = make_kpass(db, (45, doctor), (30, None), (30, nmt))

    result = found(db, kpass, patient)

    assert result.start_time == utc(14, 15)  # 14:07 rounds up to 14:15
    assert result.end_time == utc(16, 0)
    assert [(s.start_time, s.end_time) for s in result.steps] == [
        (utc(14, 15), utc(15, 0)),
        (utc(15, 0), utc(15, 30)),
        (utc(15, 30), utc(16, 0)),
    ]
    assert [s.step_id for s in result.steps] == [step.id for step in kpass.steps]
    assert [s.resource_id for s in result.steps] == [doctor.id, None, nmt.id]


def test_already_aligned_now_starts_immediately(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    assert found(db, kpass, patient, now=utc(14, 15)).start_time == utc(14, 15)


# ---------- Blocks ----------


def test_patient_block_pushes_start_later(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    block(db, utc(14, 0), utc(15, 0), patient=patient)
    assert found(db, kpass, patient).start_time == utc(15, 0)


def test_resource_block_only_affects_its_step(db):
    # Rest 30 min, then doctor 30 min. The doctor is busy until 15:00,
    # so the K-pass can start at 14:30: rest 14:30-15:00, doctor 15:00-15:30.
    patient = make_patient(db)
    doctor = make_resource(db)
    kpass = make_kpass(db, (30, None), (30, doctor))
    block(db, utc(14, 15), utc(15, 0), resource=doctor)
    result = found(db, kpass, patient)
    assert result.start_time == utc(14, 30)
    assert result.steps[1].start_time == utc(15, 0)


def test_partial_slot_block_rounds_outward(db):
    # 14:20-14:25 overlaps the 14:15-14:30 slot, so the whole slot is busy.
    patient = make_patient(db)
    kpass = make_kpass(db, (15, None))
    block(db, utc(14, 20), utc(14, 25), patient=patient)
    assert found(db, kpass, patient).start_time == utc(14, 30)


def test_other_patients_and_unused_resources_are_ignored(db):
    ann = make_patient(db, "Ann")
    bob = make_patient(db, "Bob")
    doctor = make_resource(db, "Dr. Lee")
    other_doctor = make_resource(db, "Dr. Kim")
    kpass = make_kpass(db, (30, doctor))
    block(db, utc(14, 0), utc(20, 0), patient=bob)
    block(db, utc(14, 0), utc(20, 0), resource=other_doctor)
    assert found(db, kpass, ann).start_time == utc(14, 15)


def test_same_resource_used_twice_is_checked_for_both_steps(db):
    # Doctor 30, rest 30, doctor 30. The doctor is busy 15:15-15:30.
    # 14:15 fails (second doctor step 15:15-15:45); 14:30 works (15:30-16:00).
    patient = make_patient(db)
    doctor = make_resource(db)
    kpass = make_kpass(db, (30, doctor), (30, None), (30, doctor))
    block(db, utc(15, 15), utc(15, 30), resource=doctor)
    assert found(db, kpass, patient).start_time == utc(14, 30)


def test_rest_only_kpass_depends_only_on_patient(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None), (30, None))
    block(db, utc(14, 0), utc(14, 45), patient=patient)
    assert found(db, kpass, patient).start_time == utc(14, 45)


def test_fully_blocked_returns_none(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    block(db, utc(0, 0), utc(12, 0, day=19), patient=patient)
    assert schedule(db, kpass, patient) is None


# ---------- Search window ----------


def test_default_search_end_is_midnight_in_clinic_time():
    # Midnight in New York on Nov 19 is 05:00 UTC.
    assert default_search_end(NOW) == utc(5, 0, day=19)


def test_default_window_does_not_spill_past_midnight(db):
    # Patient is free only 23:30-00:00 New York time (04:30-05:00 UTC).
    patient = make_patient(db)
    block(db, utc(14, 0), utc(4, 30, day=19), patient=patient)
    assert schedule(db, make_kpass(db, (60, None)), patient) is None
    assert found(db, make_kpass(db, (30, None)), patient).start_time == utc(4, 30, day=19)


def test_kpass_longer_than_window_raises(db):
    # 22:30 in New York leaves 90 minutes until midnight.
    patient = make_patient(db)
    kpass = make_kpass(db, (60, None), (60, None))
    with pytest.raises(ValueError, match=r"K-pass \(120 min\) is longer than the search window"):
        schedule(db, kpass, patient, now=utc(3, 30, day=19))


def test_kpass_without_steps_raises(db):
    patient = make_patient(db)
    kpass = make_kpass(db)
    with pytest.raises(ValueError, match="K-pass has no steps"):
        schedule(db, kpass, patient)


def test_custom_window_is_respected(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    result = found(db, kpass, patient, start=utc(13, 0, day=19), end=utc(18, 0, day=19))
    assert result.start_time == utc(13, 0, day=19)


def test_start_in_the_past_is_clamped_to_now(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    assert found(db, kpass, patient, start=utc(0, 0, day=1)).start_time == utc(14, 15)


def test_custom_end_cuts_off_the_search(db):
    # Free from 14:30, but a 45-minute K-pass would end at 15:15, after the 15:00 end.
    patient = make_patient(db)
    kpass = make_kpass(db, (45, None))
    block(db, utc(14, 0), utc(14, 30), patient=patient)
    assert schedule(db, kpass, patient, end=utc(15, 0)) is None


# ---------- Slot rounding ----------


@pytest.mark.parametrize(
    ("value", "floored", "ceiled"),
    [
        pytest.param(utc(9, 7), utc(9, 0), utc(9, 15), id="mid-slot"),
        pytest.param(utc(9, 0), utc(9, 0), utc(9, 0), id="aligned"),
        pytest.param(utc(9, 0) + timedelta(seconds=1), utc(9, 0), utc(9, 15), id="one-second-past"),
        pytest.param(utc(23, 50), utc(23, 45), utc(0, 0, day=19), id="midnight-rollover"),
        pytest.param(
            datetime(2026, 11, 18, 4, 7, tzinfo=timezone(timedelta(hours=-5))),
            utc(9, 0),
            utc(9, 15),
            id="non-utc-offset",
        ),
        pytest.param(datetime(2026, 11, 18, 9, 7), utc(9, 0), utc(9, 15), id="naive-is-utc"),
    ],
)
def test_slot_rounding(value, floored, ceiled):
    assert floor_to_slot(value) == floored
    assert ceil_to_slot(value) == ceiled
