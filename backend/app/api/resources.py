from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Resource
from app.db.session import DbSession
from app.schemas.resource import ResourceCreate, ResourceRead, ResourceUpdate

router = APIRouter(prefix="/resources", tags=["resources"])


def get_resource_or_404(db: Session, resource_id: int) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return resource


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def create_resource(payload: ResourceCreate, db: DbSession) -> Resource:
    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.get("", response_model=list[ResourceRead])
def list_resources(db: DbSession, type: str | None = None) -> list[Resource]:
    query = select(Resource).order_by(Resource.id)
    if type is not None:
        query = query.where(Resource.type == type)
    return list(db.scalars(query))


@router.get("/{resource_id}", response_model=ResourceRead)
def get_resource(resource_id: int, db: DbSession) -> Resource:
    return get_resource_or_404(db, resource_id)


@router.put("/{resource_id}", response_model=ResourceRead)
def update_resource(resource_id: int, payload: ResourceUpdate, db: DbSession) -> Resource:
    resource = get_resource_or_404(db, resource_id)
    for field, value in payload.model_dump().items():
        setattr(resource, field, value)
    db.commit()
    db.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(resource_id: int, db: DbSession) -> None:
    resource = get_resource_or_404(db, resource_id)
    db.delete(resource)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Resource is used by a K-pass step and cannot be deleted",
        ) from None
