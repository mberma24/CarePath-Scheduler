from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.models import Block, KPass, KPassStep, Patient, Resource
from app.scheduling.service import (
    ScheduleResult,
    book_schedule,
    ceil_to_slot,
    clinic_day_windows,
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
    """Each step is a (duration_minutes, resource) pair, in order.

    resource is a Resource, a type string (any resource of that type), or None (rest).
    """
    kpass = KPass(
        name="Test K-pass",
        steps=[
            KPassStep(
                position=i,
                name=f"Step {i}",
                duration_minutes=minutes,
                resource=None if isinstance(resource, str) else resource,
                resource_type=resource if isinstance(resource, str) else None,
            )
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
    assert schedule(db, kpass, patient) is None  # horizon is 1 day in tests


# ---------- Search window ----------


def test_default_search_end_is_midnight_in_clinic_time():
    # Midnight in New York on Nov 19 is 05:00 UTC.
    assert default_search_end(NOW) == utc(5, 0, day=19)


def test_default_search_end_counts_horizon_from_the_start_day(monkeypatch):
    monkeypatch.setattr(settings, "schedule_horizon_days", 7)
    assert default_search_end(NOW) == utc(5, 0, day=25)
    assert default_search_end(utc(15, 0, day=20)) == utc(5, 0, day=27)


# ---------- Clinic hours (7:00-19:00 New York = 12:00-00:00 UTC in November) ----------


def test_never_starts_before_opening(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    # 5:00 in New York
    assert found(db, kpass, patient, now=utc(10, 0)).start_time == utc(12, 0)


def test_never_runs_past_closing(db):
    # Patient is free only 18:30-19:00 New York time (23:30-00:00 UTC).
    patient = make_patient(db)
    block(db, utc(14, 0), utc(23, 30), patient=patient)
    assert schedule(db, make_kpass(db, (60, None)), patient) is None
    assert found(db, make_kpass(db, (30, None)), patient).start_time == utc(23, 30)


def test_rolls_over_to_the_next_clinic_day(db, monkeypatch):
    monkeypatch.setattr(settings, "schedule_horizon_days", 2)
    patient = make_patient(db)
    block(db, utc(14, 0), utc(0, 0, day=19), patient=patient)  # rest of today
    result = found(db, make_kpass(db, (60, None)), patient)
    assert (result.start_time, result.end_time) == (utc(12, 0, day=19), utc(13, 0, day=19))


def test_multi_day_horizon_finds_a_slot_on_day_three(db, monkeypatch):
    monkeypatch.setattr(settings, "schedule_horizon_days", 7)
    patient = make_patient(db)
    doctor = make_resource(db)
    block(db, utc(14, 0), utc(0, 0, day=21), resource=doctor)  # busy until day 3
    result = found(db, make_kpass(db, (45, doctor)), patient)
    assert result.start_time == utc(12, 0, day=21)


def test_horizon_of_one_day_does_not_look_further(db):
    patient = make_patient(db)
    doctor = make_resource(db)
    block(db, utc(14, 0), utc(0, 0, day=19), resource=doctor)
    assert schedule(db, make_kpass(db, (45, doctor)), patient) is None


def test_clinic_hours_follow_daylight_saving():
    # Daylight saving ends Nov 1, 2026: 7:00 New York is 11:00 UTC on Oct 31, 12:00 UTC on Nov 2.
    windows = clinic_day_windows(
        datetime(2026, 10, 31, 0, 0, tzinfo=UTC), datetime(2026, 11, 3, 6, 0, tzinfo=UTC)
    )
    assert [(s.astimezone(UTC).hour, e.astimezone(UTC).hour) for s, e in windows] == [
        (11, 23),  # Oct 31 (EDT)
        (12, 0),  # Nov 1 (EST)
        (12, 0),  # Nov 2
    ]


def test_step_not_a_multiple_of_the_slot_raises(db, monkeypatch):
    # A 45-minute step saved earlier must not silently become 30 minutes after a slot change.
    patient = make_patient(db)
    kpass = make_kpass(db, (45, None))
    monkeypatch.setattr(settings, "slot_minutes", 30)
    with pytest.raises(ValueError, match=r"Step 'Step 0' \(45 min\) isn't a multiple"):
        schedule(db, kpass, patient)


def test_kpass_longer_than_a_clinic_day_raises(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (12 * 60 + 15, None))
    with pytest.raises(ValueError, match=r"longer than a clinic day \(720 min\)"):
        schedule(db, kpass, patient)


def test_no_day_with_enough_room_returns_none(db):
    # 18:00 in New York leaves 60 minutes until closing, and the horizon is 1 day:
    # that is "no slot", not an error (e.g. pressing Next slot at the end of the range).
    patient = make_patient(db)
    kpass = make_kpass(db, (60, None), (60, None))
    assert schedule(db, kpass, patient, now=utc(23, 0)) is None


# ---------- Booking ----------


def test_booking_a_start_that_has_passed_books_nothing(db):
    # 14:00 is before NOW (14:07); the booking must not move to a later time.
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    with pytest.raises(ValueError):
        book_schedule(db, kpass, patient, utc(14, 0), now=NOW)
    assert db.scalars(select(Block)).all() == []


def test_booking_a_passed_start_says_so(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    with pytest.raises(ValueError, match="already passed"):
        book_schedule(db, kpass, patient, utc(14, 0), now=NOW)


def test_booking_books_exactly_the_requested_start(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    result = book_schedule(db, kpass, patient, utc(15, 0), now=NOW)
    assert result is not None and result.start_time == utc(15, 0)


def test_booking_outside_clinic_hours_books_nothing(db):
    patient = make_patient(db)
    kpass = make_kpass(db, (30, None))
    assert book_schedule(db, kpass, patient, utc(2, 0, day=19), now=NOW) is None  # 21:00 NY
    assert db.scalars(select(Block)).all() == []


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


# ---------- Any resource of a type ----------


def test_type_step_uses_first_free_resource(db):
    patient = make_patient(db)
    lee = make_resource(db, "Dr. Lee", "doctor")
    kim = make_resource(db, "Dr. Kim", "doctor")
    kpass = make_kpass(db, (30, "doctor"))
    block(db, utc(14, 0), utc(16, 0), resource=lee)

    result = found(db, kpass, patient)

    assert result.start_time == utc(14, 15)
    assert result.steps[0].resource_id == kim.id


def test_type_step_prefers_lowest_id_when_all_free(db):
    patient = make_patient(db)
    lee = make_resource(db, "Dr. Lee", "doctor")
    make_resource(db, "Dr. Kim", "doctor")
    kpass = make_kpass(db, (30, "doctor"))

    assert found(db, kpass, patient).steps[0].resource_id == lee.id


def test_type_step_waits_until_any_resource_is_free(db):
    patient = make_patient(db)
    lee = make_resource(db, "Dr. Lee", "doctor")
    kim = make_resource(db, "Dr. Kim", "doctor")
    kpass = make_kpass(db, (30, "doctor"))
    block(db, utc(14, 0), utc(16, 0), resource=lee)
    block(db, utc(14, 0), utc(15, 0), resource=kim)

    result = found(db, kpass, patient)

    assert result.start_time == utc(15, 0)
    assert result.steps[0].resource_id == kim.id


def test_type_step_needs_one_resource_for_the_whole_step(db):
    # Lee is free 14:15-14:30 and Kim 14:30-14:45: every slot has a free doctor,
    # but no single doctor covers 14:15-14:45, so the step starts once Kim is free for 30 min.
    patient = make_patient(db)
    lee = make_resource(db, "Dr. Lee", "doctor")
    kim = make_resource(db, "Dr. Kim", "doctor")
    kpass = make_kpass(db, (30, "doctor"))
    block(db, utc(14, 30), utc(18, 0), resource=lee)
    block(db, utc(14, 0), utc(14, 30), resource=kim)

    result = found(db, kpass, patient)

    assert result.start_time == utc(14, 30)
    assert result.steps[0].resource_id == kim.id


def test_type_step_all_resources_blocked_returns_none(db):
    patient = make_patient(db)
    lee = make_resource(db, "Dr. Lee", "doctor")
    kim = make_resource(db, "Dr. Kim", "doctor")
    kpass = make_kpass(db, (30, "doctor"))
    block(db, utc(14, 0), utc(16, 0), resource=lee)
    block(db, utc(14, 0), utc(16, 0), resource=kim)

    assert schedule(db, kpass, patient, end=utc(16, 0)) is None


def test_type_with_no_resources_raises(db):
    # Explains why nothing can be found, instead of a silent "no slot".
    patient = make_patient(db)
    kpass = make_kpass(db, (30, "scanner"))
    with pytest.raises(ValueError, match="No resources of type 'scanner'"):
        schedule(db, kpass, patient)


def test_type_step_mixed_with_specific_resource(db):
    patient = make_patient(db)
    lee = make_resource(db, "Dr. Lee", "doctor")
    sam = make_resource(db, "Sam", "nmt")
    pat = make_resource(db, "Pat", "nmt")
    kpass = make_kpass(db, (30, lee), (30, "nmt"))
    block(db, utc(14, 0), utc(18, 0), resource=sam)

    result = found(db, kpass, patient)

    assert [s.resource_id for s in result.steps] == [lee.id, pat.id]
    assert result.start_time == utc(14, 15)


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
