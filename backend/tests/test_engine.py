import pytest

from app.scheduling.engine import Step, find_earliest_start

PATIENT, DOCTOR, NMT = 0, 1, 2  # row indexes


# ---------- Invalid input (preconditions) ----------


@pytest.mark.parametrize(
    ("kpass", "schedule", "message"),
    [
        pytest.param([], [[0, 0]], "kpass must not be empty", id="empty-kpass"),
        pytest.param([Step(1, None)], [], "schedule must not be empty", id="empty-schedule"),
        pytest.param([], [], "kpass must not be empty", id="both-empty"),
        pytest.param([Step(1, DOCTOR)], [[0, 0, 0], [0, 0]], "row 1 has 2 slots", id="ragged-rows"),
        pytest.param([Step(1, None)], [[0, 2, 0]], "values other than 0 and 1", id="value-2"),
        pytest.param(
            [Step(1, None)], [[0, -1, 0]], "values other than 0 and 1", id="value-negative"
        ),
        pytest.param([Step(0, None)], [[0, 0]], "non-positive duration", id="zero-duration"),
        pytest.param([Step(-2, None)], [[0, 0]], "non-positive duration", id="negative-duration"),
        pytest.param([Step(1, 0)], [[0, 0]], "resource row 0", id="resource-is-patient-row"),
        pytest.param([Step(1, 2)], [[0, 0], [0, 0]], "resource row 2", id="resource-row-too-large"),
        pytest.param(
            [Step(1, -1)], [[0, 0], [0, 0]], "resource row -1", id="resource-row-negative"
        ),
        pytest.param(
            [Step(1, None), Step(1, 5)], [[0, 0, 0]], "step 1 references", id="later-step-bad-row"
        ),
    ],
)
def test_invalid_input_raises(kpass, schedule, message):
    with pytest.raises(ValueError, match=message):
        find_earliest_start(kpass, schedule)


# ---------- Valid input, no availability ----------


def test_kpass_longer_than_schedule_returns_none():
    assert find_earliest_start([Step(3, DOCTOR)], [[0, 0], [0, 0]]) is None


def test_zero_column_schedule_returns_none():
    assert find_earliest_start([Step(1, None)], [[]]) is None


def test_no_window_fits_returns_none():
    schedule = [
        [0, 0, 0, 0],  # patient
        [0, 1, 0, 1],  # doctor: never free 2 in a row
    ]
    assert find_earliest_start([Step(2, DOCTOR)], schedule) is None


def test_patient_always_busy_returns_none():
    schedule = [
        [1, 1, 1],  # patient
        [0, 0, 0],  # doctor
    ]
    assert find_earliest_start([Step(3, DOCTOR)], schedule) is None


# ---------- Valid input, finds a start ----------


def test_everything_free_starts_at_zero():
    assert find_earliest_start([Step(2, DOCTOR)], [[0] * 4, [0] * 4]) == 0


def test_resource_busy_at_start_shifts_start():
    schedule = [
        [0, 0, 0, 0, 0, 0],  # patient
        [1, 1, 0, 0, 0, 0],  # doctor
    ]
    assert find_earliest_start([Step(2, DOCTOR)], schedule) == 2


def test_exact_fit_at_end_of_schedule():
    schedule = [
        [0, 0, 0, 0],  # patient
        [1, 1, 0, 0],  # doctor: only the last 2 slots free
    ]
    assert find_earliest_start([Step(2, DOCTOR)], schedule) == 2


def test_rest_step_ignores_resource_busy():
    schedule = [
        [0, 0, 0, 0],  # patient
        [0, 1, 1, 0],  # doctor: busy only during the rest
        [0, 0, 0, 0],  # nmt
    ]
    kpass = [Step(1, DOCTOR), Step(2, None), Step(1, NMT)]
    assert find_earliest_start(kpass, schedule) == 0


def test_patient_busy_midway_shifts_start():
    schedule = [[0, 1, 0, 0, 0]]  # patient only
    kpass = [Step(1, None), Step(1, None)]
    assert find_earliest_start(kpass, schedule) == 2


def test_busy_slot_just_after_window_does_not_block():
    schedule = [
        [0, 0, 1, 0],  # patient: busy right after the window
        [0, 0, 0, 0],  # doctor
    ]
    assert find_earliest_start([Step(2, DOCTOR)], schedule) == 0


def test_same_resource_used_by_multiple_steps():
    schedule = [
        [0, 0, 0, 0],  # patient
        [0, 1, 0, 0],  # doctor
    ]
    kpass = [Step(1, DOCTOR), Step(1, DOCTOR)]
    assert find_earliest_start(kpass, schedule) == 2


def test_unused_resource_rows_are_ignored():
    schedule = [
        [0, 0],  # patient
        [0, 0],  # doctor
        [1, 1],  # nmt: busy, but not in the kpass
    ]
    assert find_earliest_start([Step(1, DOCTOR)], schedule) == 0


def test_second_resource_free_at_its_offset():
    schedule = [
        [0] * 6,  # patient
        [0] * 6,  # doctor
        [1, 1, 0, 0, 0, 0],  # nmt: free by its step's offset (2)
    ]
    kpass = [Step(1, DOCTOR), Step(1, None), Step(1, NMT)]
    assert find_earliest_start(kpass, schedule) == 0


def test_second_resource_conflict_shifts_start():
    schedule = [
        [0] * 6,  # patient
        [0] * 6,  # doctor
        [1, 1, 1, 0, 0, 0],  # nmt: busy at offset 2 when t=0
    ]
    kpass = [Step(1, DOCTOR), Step(1, None), Step(1, NMT)]
    assert find_earliest_start(kpass, schedule) == 1
