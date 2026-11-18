from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patient"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))

    blocks: Mapped[list["Block"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class Resource(Base):
    __tablename__ = "resource"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50))

    blocks: Mapped[list["Block"]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )


class CarePath(Base):
    __tablename__ = "care_path"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))

    steps: Mapped[list["CarePathStep"]] = relationship(
        back_populates="care_path",
        order_by="CarePathStep.position",
        cascade="all, delete-orphan",
    )


class CarePathStep(Base):
    __tablename__ = "care_path_step"
    __table_args__ = (
        UniqueConstraint("care_path_id", "position"),
        CheckConstraint("duration_minutes > 0", name="ck_step_positive_duration"),
        CheckConstraint(
            "resource_id IS NULL OR resource_type IS NULL", name="ck_step_one_resource_kind"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    care_path_id: Mapped[int] = mapped_column(ForeignKey("care_path.id", ondelete="CASCADE"))
    position: Mapped[int]
    name: Mapped[str] = mapped_column(String(200))
    duration_minutes: Mapped[int]
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resource.id"))  # one resource
    resource_type: Mapped[str | None] = mapped_column(String(50))  # or any resource of this type

    care_path: Mapped["CarePath"] = relationship(back_populates="steps")
    resource: Mapped["Resource | None"] = relationship()


class Block(Base):
    """A time interval when a patient OR a resource is unavailable."""

    __tablename__ = "block"
    __table_args__ = (
        CheckConstraint(
            "(patient_id IS NULL) != (resource_id IS NULL)",
            name="ck_block_exactly_one_owner",
        ),
        CheckConstraint("end_time > start_time", name="ck_block_end_after_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200))
    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("patient.id", ondelete="CASCADE"), index=True
    )
    resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("resource.id", ondelete="CASCADE"), index=True
    )

    patient: Mapped["Patient | None"] = relationship(back_populates="blocks")
    resource: Mapped["Resource | None"] = relationship(back_populates="blocks")
