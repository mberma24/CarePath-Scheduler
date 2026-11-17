from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import KPass, KPassStep, Resource
from app.db.session import DbSession
from app.schemas.kpass import (
    KPassCreate,
    KPassRead,
    KPassStepCreate,
    KPassStepOrder,
    KPassStepUpdate,
    KPassUpdate,
)

router = APIRouter(prefix="/kpasses", tags=["kpasses"])


def get_kpass_or_404(db: Session, kpass_id: int) -> KPass:
    kpass = db.get(KPass, kpass_id)
    if kpass is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "K-pass not found")
    return kpass


def get_step_or_404(db: Session, kpass: KPass, step_id: int) -> KPassStep:
    step = db.get(KPassStep, step_id)
    if step is None or step.kpass_id != kpass.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    return step


def ensure_resource_exists(db: Session, resource_id: int | None) -> None:
    if resource_id is not None and db.get(Resource, resource_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Resource not found")


def renumber_steps(db: Session, steps: list[KPassStep]) -> None:
    """Set positions to 0..n-1 in list order without breaking the unique constraint."""
    # Phase 1: move every step to a unique negative position. These can't collide
    # with each other or with any real (non-negative) position still in the table.
    for i, step in enumerate(steps):
        step.position = -(i + 1)
    db.flush()

    # Phase 2: no row holds a non-negative position now, so assign the final ones.
    for i, step in enumerate(steps):
        step.position = i


@router.post("", response_model=KPassRead, status_code=status.HTTP_201_CREATED)
def create_kpass(payload: KPassCreate, db: DbSession) -> KPass:
    kpass = KPass(**payload.model_dump())
    db.add(kpass)
    db.commit()
    db.refresh(kpass)
    return kpass


@router.get("", response_model=list[KPassRead])
def list_kpasses(db: DbSession) -> list[KPass]:
    query = select(KPass).options(selectinload(KPass.steps)).order_by(KPass.id)
    return list(db.scalars(query))


@router.get("/{kpass_id}", response_model=KPassRead)
def get_kpass(kpass_id: int, db: DbSession) -> KPass:
    return get_kpass_or_404(db, kpass_id)


@router.put("/{kpass_id}", response_model=KPassRead)
def update_kpass(kpass_id: int, payload: KPassUpdate, db: DbSession) -> KPass:
    kpass = get_kpass_or_404(db, kpass_id)
    for field, value in payload.model_dump().items():
        setattr(kpass, field, value)
    db.commit()
    db.refresh(kpass)
    return kpass


@router.delete("/{kpass_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kpass(kpass_id: int, db: DbSession) -> None:
    kpass = get_kpass_or_404(db, kpass_id)
    db.delete(kpass)
    db.commit()


@router.post(
    "/{kpass_id}/steps",
    response_model=KPassRead,
    status_code=status.HTTP_201_CREATED,
)
def add_step(kpass_id: int, payload: KPassStepCreate, db: DbSession) -> KPass:
    kpass = get_kpass_or_404(db, kpass_id)
    ensure_resource_exists(db, payload.resource_id)

    num_steps = len(kpass.steps)
    index = num_steps if payload.position is None else min(payload.position, num_steps)

    # Temporary unique negative position; renumber_steps sets the real one.
    step = KPassStep(**payload.model_dump(exclude={"position"}), position=-(num_steps + 1))
    kpass.steps.insert(index, step)

    renumber_steps(db, kpass.steps)
    db.commit()
    db.refresh(kpass)
    return kpass


@router.put("/{kpass_id}/steps/{step_id}", response_model=KPassRead)
def update_step(kpass_id: int, step_id: int, payload: KPassStepUpdate, db: DbSession) -> KPass:
    kpass = get_kpass_or_404(db, kpass_id)
    step = get_step_or_404(db, kpass, step_id)
    ensure_resource_exists(db, payload.resource_id)

    for field, value in payload.model_dump().items():
        setattr(step, field, value)

    db.commit()
    db.refresh(kpass)
    return kpass


@router.delete("/{kpass_id}/steps/{step_id}", response_model=KPassRead)
def delete_step(kpass_id: int, step_id: int, db: DbSession) -> KPass:
    kpass = get_kpass_or_404(db, kpass_id)
    step = get_step_or_404(db, kpass, step_id)

    # Removing it from the list deletes it on flush (cascade="all, delete-orphan").
    # Returns 200 with the K-pass, not 204, because the other steps' positions change.
    kpass.steps.remove(step)

    renumber_steps(db, kpass.steps)
    db.commit()
    db.refresh(kpass)
    return kpass


@router.put("/{kpass_id}/steps", response_model=KPassRead)
def reorder_steps(kpass_id: int, payload: KPassStepOrder, db: DbSession) -> KPass:
    kpass = get_kpass_or_404(db, kpass_id)
    steps_by_id = {step.id: step for step in kpass.steps}

    # Must be every step of this K-pass exactly once: no missing, extra, or duplicate IDs.
    if len(payload.step_ids) != len(steps_by_id) or set(payload.step_ids) != set(steps_by_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "step_ids must list every step of this K-pass exactly once",
        )

    kpass.steps = [steps_by_id[step_id] for step_id in payload.step_ids]

    renumber_steps(db, kpass.steps)
    db.commit()
    db.refresh(kpass)
    return kpass
