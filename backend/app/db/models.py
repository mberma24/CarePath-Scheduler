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


class KPass(Base):
    __tablename__ = "kpass"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))

    steps: Mapped[list["KPassStep"]] = relationship(
        back_populates="kpass",
        order_by="KPassStep.position",
        cascade="all, delete-orphan",
    )


class KPassStep(Base):
    __tablename__ = "kpass_step"
    __table_args__ = (
        UniqueConstraint("kpass_id", "position"),
        CheckConstraint("duration_minutes > 0", name="ck_step_positive_duration"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kpass_id: Mapped[int] = mapped_column(ForeignKey("kpass.id", ondelete="CASCADE"))
    position: Mapped[int]
    name: Mapped[str] = mapped_column(String(200))
    duration_minutes: Mapped[int]
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("resource.id"))  # None = rest

    kpass: Mapped["KPass"] = relationship(back_populates="steps")
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
