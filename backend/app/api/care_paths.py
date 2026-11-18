from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import CarePath, CarePathStep, Resource
from app.db.session import DbSession
from app.schemas.care_path import (
    CLINIC_DAY_MINUTES,
    CarePathCreate,
    CarePathRead,
    CarePathStepCreate,
    CarePathStepOrder,
    CarePathStepUpdate,
    CarePathUpdate,
)

router = APIRouter(prefix="/care-paths", tags=["care_paths"])


def get_care_path_or_404(db: Session, care_path_id: int) -> CarePath:
    care_path = db.get(CarePath, care_path_id)
    if care_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Care path not found")
    return care_path


def get_step_or_404(db: Session, care_path: CarePath, step_id: int) -> CarePathStep:
    step = db.get(CarePathStep, step_id)
    if step is None or step.care_path_id != care_path.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    return step


def ensure_resource_exists(db: Session, resource_id: int | None) -> None:
    if resource_id is not None and db.get(Resource, resource_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Resource not found")


def ensure_resource_type_exists(db: Session, resource_type: str | None) -> None:
    if (
        resource_type is not None
        and db.scalar(select(Resource.id).where(Resource.type == resource_type).limit(1)) is None
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"No resources of type '{resource_type}'"
        )


def care_path_total(care_path: CarePath) -> int:
    return sum(step.duration_minutes for step in care_path.steps)


def ensure_fits_clinic_day(total_minutes: int) -> None:
    """A care path longer than a clinic day could never be scheduled, so reject it up front."""
    if total_minutes > CLINIC_DAY_MINUTES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Care path would be {total_minutes} min, longer than a clinic day "
            f"({CLINIC_DAY_MINUTES} min)",
        )


def renumber_steps(db: Session, steps: list[CarePathStep]) -> None:
    """Set positions to 0..n-1 in list order without breaking the unique constraint."""
    # Phase 1: move every step to a unique negative position. These can't collide
    # with each other or with any real (non-negative) position still in the table.
    for i, step in enumerate(steps):
        step.position = -(i + 1)
    db.flush()

    # Phase 2: no row holds a non-negative position now, so assign the final ones.
    for i, step in enumerate(steps):
        step.position = i


@router.post("", response_model=CarePathRead, status_code=status.HTTP_201_CREATED)
def create_care_path(payload: CarePathCreate, db: DbSession) -> CarePath:
    care_path = CarePath(**payload.model_dump())
    db.add(care_path)
    db.commit()
    db.refresh(care_path)
    return care_path


@router.get("", response_model=list[CarePathRead])
def list_care_paths(db: DbSession) -> list[CarePath]:
    query = select(CarePath).options(selectinload(CarePath.steps)).order_by(CarePath.id)
    return list(db.scalars(query))


@router.get("/{care_path_id}", response_model=CarePathRead)
def get_care_path(care_path_id: int, db: DbSession) -> CarePath:
    return get_care_path_or_404(db, care_path_id)


@router.put("/{care_path_id}", response_model=CarePathRead)
def update_care_path(care_path_id: int, payload: CarePathUpdate, db: DbSession) -> CarePath:
    care_path = get_care_path_or_404(db, care_path_id)
    for field, value in payload.model_dump().items():
        setattr(care_path, field, value)
    db.commit()
    db.refresh(care_path)
    return care_path


@router.delete("/{care_path_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_care_path(care_path_id: int, db: DbSession) -> None:
    care_path = get_care_path_or_404(db, care_path_id)
    db.delete(care_path)
    db.commit()


@router.post(
    "/{care_path_id}/steps",
    response_model=CarePathRead,
    status_code=status.HTTP_201_CREATED,
)
def add_step(care_path_id: int, payload: CarePathStepCreate, db: DbSession) -> CarePath:
    care_path = get_care_path_or_404(db, care_path_id)
    ensure_resource_exists(db, payload.resource_id)
    ensure_resource_type_exists(db, payload.resource_type)
    ensure_fits_clinic_day(care_path_total(care_path) + payload.duration_minutes)

    num_steps = len(care_path.steps)
    index = num_steps if payload.position is None else min(payload.position, num_steps)

    # Temporary unique negative position; renumber_steps sets the real one.
    step = CarePathStep(**payload.model_dump(exclude={"position"}), position=-(num_steps + 1))
    care_path.steps.insert(index, step)

    renumber_steps(db, care_path.steps)
    db.commit()
    db.refresh(care_path)
    return care_path


@router.put("/{care_path_id}/steps/{step_id}", response_model=CarePathRead)
def update_step(
    care_path_id: int, step_id: int, payload: CarePathStepUpdate, db: DbSession
) -> CarePath:
    care_path = get_care_path_or_404(db, care_path_id)
    step = get_step_or_404(db, care_path, step_id)
    ensure_resource_exists(db, payload.resource_id)
    ensure_resource_type_exists(db, payload.resource_type)
    ensure_fits_clinic_day(
        care_path_total(care_path) - step.duration_minutes + payload.duration_minutes
    )

    for field, value in payload.model_dump().items():
        setattr(step, field, value)

    db.commit()
    db.refresh(care_path)
    return care_path


@router.delete("/{care_path_id}/steps/{step_id}", response_model=CarePathRead)
def delete_step(care_path_id: int, step_id: int, db: DbSession) -> CarePath:
    care_path = get_care_path_or_404(db, care_path_id)
    step = get_step_or_404(db, care_path, step_id)

    # Removing it from the list deletes it on flush (cascade="all, delete-orphan").
    # Returns 200 with the care path, not 204, because the other steps' positions change.
    care_path.steps.remove(step)

    renumber_steps(db, care_path.steps)
    db.commit()
    db.refresh(care_path)
    return care_path


@router.put("/{care_path_id}/steps", response_model=CarePathRead)
def reorder_steps(care_path_id: int, payload: CarePathStepOrder, db: DbSession) -> CarePath:
    care_path = get_care_path_or_404(db, care_path_id)
    steps_by_id = {step.id: step for step in care_path.steps}

    # Must be every step of this care path exactly once: no missing, extra, or duplicate IDs.
    if len(payload.step_ids) != len(steps_by_id) or set(payload.step_ids) != set(steps_by_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "step_ids must list every step of this care path exactly once",
        )

    care_path.steps = [steps_by_id[step_id] for step_id in payload.step_ids]

    renumber_steps(db, care_path.steps)
    db.commit()
    db.refresh(care_path)
    return care_path
