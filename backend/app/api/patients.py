from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Patient
from app.db.session import DbSession
from app.schemas.patient import PatientCreate, PatientRead, PatientUpdate

router = APIRouter(prefix="/patients", tags=["patients"])


def get_patient_or_404(db: Session, patient_id: int) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    return patient


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, db: DbSession) -> Patient:
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=list[PatientRead])
def list_patients(db: DbSession) -> list[Patient]:
    return list(db.scalars(select(Patient).order_by(Patient.id)))


@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(patient_id: int, db: DbSession) -> Patient:
    return get_patient_or_404(db, patient_id)


@router.put("/{patient_id}", response_model=PatientRead)
def update_patient(patient_id: int, payload: PatientUpdate, db: DbSession) -> Patient:
    patient = get_patient_or_404(db, patient_id)
    for field, value in payload.model_dump().items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(patient_id: int, db: DbSession) -> None:
    patient = get_patient_or_404(db, patient_id)
    db.delete(patient)
    db.commit()
