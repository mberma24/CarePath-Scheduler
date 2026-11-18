from fastapi import APIRouter, HTTPException, status

from app.api.care_paths import get_care_path_or_404
from app.api.patients import get_patient_or_404
from app.db.session import DbSession
from app.scheduling.service import ScheduleResult, book_schedule, find_earliest_schedule
from app.schemas.schedule import BookRequest, ScheduledStepRead, ScheduleRequest, ScheduleResponse

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("", response_model=ScheduleResponse)
def find_schedule(payload: ScheduleRequest, db: DbSession) -> ScheduleResponse:
    care_path = get_care_path_or_404(db, payload.care_path_id)
    patient = get_patient_or_404(db, payload.patient_id)

    try:
        result = find_earliest_schedule(
            db, care_path, patient, start=payload.start, end=payload.end
        )
    except ValueError as error:
        # No steps, or the care path is longer than the search window.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None

    # No slot in the window is a normal answer, not an error.
    if result is None:
        return ScheduleResponse(found=False)

    return to_response(result)


@router.post("/book", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def book(payload: BookRequest, db: DbSession) -> ScheduleResponse:
    """Book a slot found by POST /schedule: blocks the patient and each step's resource."""
    care_path = get_care_path_or_404(db, payload.care_path_id)
    patient = get_patient_or_404(db, payload.patient_id)

    try:
        result = book_schedule(db, care_path, patient, payload.start)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None

    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That slot is no longer available")

    return to_response(result)


def to_response(result: ScheduleResult) -> ScheduleResponse:
    return ScheduleResponse(
        found=True,
        start_time=result.start_time,
        end_time=result.end_time,
        steps=[ScheduledStepRead.model_validate(step) for step in result.steps],
    )
