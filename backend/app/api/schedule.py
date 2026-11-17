from fastapi import APIRouter, HTTPException, status

from app.api.kpasses import get_kpass_or_404
from app.api.patients import get_patient_or_404
from app.db.session import DbSession
from app.scheduling.service import find_earliest_schedule
from app.schemas.schedule import ScheduledStepRead, ScheduleRequest, ScheduleResponse

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("", response_model=ScheduleResponse)
def find_schedule(payload: ScheduleRequest, db: DbSession) -> ScheduleResponse:
    kpass = get_kpass_or_404(db, payload.kpass_id)
    patient = get_patient_or_404(db, payload.patient_id)

    try:
        result = find_earliest_schedule(db, kpass, patient, start=payload.start, end=payload.end)
    except ValueError as error:
        # No steps, or the K-pass is longer than the search window.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None

    # No slot in the window is a normal answer, not an error.
    if result is None:
        return ScheduleResponse(found=False)

    return ScheduleResponse(
        found=True,
        start_time=result.start_time,
        end_time=result.end_time,
        steps=[ScheduledStepRead.model_validate(step) for step in result.steps],
    )
