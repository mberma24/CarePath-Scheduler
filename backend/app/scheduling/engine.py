from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    duration_slots: int
    resource_row: int | None  # None = rest step


def validate_inputs(kpass: list[Step], schedule: list[list[int]]) -> None:
    """
    Raise ValueError if the inputs break the engine's preconditions.
    """

    # if either kpass or schedule do not exist
    if not kpass:
        raise ValueError("kpass must not be empty")
    if not schedule:
        raise ValueError("schedule must not be empty")

    # ensure all schedule rows are the same size and all inputs are 0 or 1
    num_slots = len(schedule[0])
    for i, row in enumerate(schedule):
        if len(row) != num_slots:
            raise ValueError(f"schedule row {i} has {len(row)} slots, expected {num_slots}")
        if any(cell not in (0, 1) for cell in row):
            raise ValueError(f"schedule row {i} contains values other than 0 and 1")

    for i, step in enumerate(kpass):
        if step.duration_slots <= 0:
            raise ValueError(f"step {i} has non-positive duration {step.duration_slots}")
        if step.resource_row is not None and not 0 < step.resource_row < len(schedule):
            raise ValueError(
                f"kpass step {i} references resource row {step.resource_row}, "
                "which is not in the schedule"
            )


def find_earliest_start(
    kpass: list[Step],
    schedule: list[list[int]],
) -> int | None:
    """
    Return the earliest start slot where all steps fit back-to-back, or None if none fit.

    kpass: ordered steps.
    schedule: row 0 = patient, rows 1..n = resources; 1 = busy, 0 = free.
    """
    validate_inputs(kpass=kpass, schedule=schedule)

    total_duration = sum(step.duration_slots for step in kpass)
    num_slots = len(schedule[0])  # number of slots in the schedule
    if total_duration > num_slots:
        return None  # not enough slots in the schedule to fit the kpass

    num_busy_slots = 0  # total number of busy slots in the current window

    # STARTUP PHASE
    offset = 0
    for step in kpass:
        duration = step.duration_slots

        # for each step we must check the patient's busy slots and the resource's busy slots
        num_busy_slots += sum(schedule[0][offset : offset + duration])
        if step.resource_row is not None:
            num_busy_slots += sum(schedule[step.resource_row][offset : offset + duration])

        offset += duration

    if num_busy_slots == 0:
        return 0  # the first window is free

    # SLIDING WINDOW PHASE
    for t in range(1, num_slots - total_duration + 1):
        # update patient availablity
        num_busy_slots -= schedule[0][t - 1]
        num_busy_slots += schedule[0][t + total_duration - 1]

        # update resource availablity
        offset = 0
        for step in kpass:
            if step.resource_row is not None:
                row = schedule[step.resource_row]
                num_busy_slots -= row[t - 1 + offset]
                num_busy_slots += row[t - 1 + offset + step.duration_slots]
            offset += step.duration_slots
        if num_busy_slots == 0:
            return t

    return None
