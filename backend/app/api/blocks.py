from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Block, Patient, Resource
from app.db.session import DbSession
from app.scheduling.service import floor_to_slot
from app.schemas.block import BlockCreate, BlockRead, BlockUpdate

router = APIRouter(prefix="/blocks", tags=["blocks"])


def get_block_or_404(db: Session, block_id: int) -> Block:
    block = db.get(Block, block_id)
    if block is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Block not found")
    return block


def ensure_owner_exists(db: Session, patient_id: int | None, resource_id: int | None) -> None:
    if patient_id is not None and db.get(Patient, patient_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Patient not found")
    if resource_id is not None and db.get(Resource, resource_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Resource not found")


def ensure_not_in_past(start: datetime) -> None:
    """Blocks can't start before the current slot (the slot happening now is still allowed)."""
    if start.astimezone(UTC) < floor_to_slot(datetime.now(UTC)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Can't block time in the past")


def ensure_no_overlap(
    db: Session,
    patient_id: int | None,
    resource_id: int | None,
    start: datetime,
    end: datetime,
    exclude_id: int | None = None,
) -> None:
    """409 if the owner already has a block overlapping [start, end). Back-to-back is fine."""
    query = select(Block.id).where(
        Block.patient_id == patient_id
        if patient_id is not None
        else Block.resource_id == resource_id,
        Block.end_time > start.astimezone(UTC),
        Block.start_time < end.astimezone(UTC),
    )
    if exclude_id is not None:
        query = query.where(Block.id != exclude_id)
    if db.scalar(query.limit(1)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Overlaps an existing block")


@router.post("", response_model=BlockRead, status_code=status.HTTP_201_CREATED)
def create_block(payload: BlockCreate, db: DbSession) -> Block:
    ensure_owner_exists(db, payload.patient_id, payload.resource_id)
    ensure_not_in_past(payload.start_time)
    ensure_no_overlap(
        db, payload.patient_id, payload.resource_id, payload.start_time, payload.end_time
    )
    block = Block(**payload.model_dump())
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.get("", response_model=list[BlockRead])
def list_blocks(
    db: DbSession,
    patient_id: int | None = None,
    resource_id: int | None = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
) -> list[Block]:
    query = select(Block)
    if patient_id is not None:
        query = query.where(Block.patient_id == patient_id)
    if resource_id is not None:
        query = query.where(Block.resource_id == resource_id)

    # Return blocks that overlap [start, end), including ones that cross either edge.
    # Times are stored as UTC, so convert before comparing.
    if start is not None:
        query = query.where(Block.end_time > start.astimezone(UTC))
    if end is not None:
        query = query.where(Block.start_time < end.astimezone(UTC))

    return list(db.scalars(query.order_by(Block.start_time, Block.id)))


@router.get("/{block_id}", response_model=BlockRead)
def get_block(block_id: int, db: DbSession) -> Block:
    return get_block_or_404(db, block_id)


@router.put("/{block_id}", response_model=BlockRead)
def update_block(block_id: int, payload: BlockUpdate, db: DbSession) -> Block:
    block = get_block_or_404(db, block_id)
    ensure_not_in_past(payload.start_time)
    ensure_no_overlap(
        db,
        block.patient_id,
        block.resource_id,
        payload.start_time,
        payload.end_time,
        exclude_id=block.id,
    )
    for field, value in payload.model_dump().items():
        setattr(block, field, value)
    db.commit()
    db.refresh(block)
    return block


@router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(block_id: int, db: DbSession) -> None:
    block = get_block_or_404(db, block_id)
    db.delete(block)
    db.commit()
