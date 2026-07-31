"""Case model."""

import uuid

from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Enum
from app.utils import utc_now
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol_number = Column(String(50), unique=True, nullable=False)
    inquiry_number = Column(String(100), nullable=True)
    process_number = Column(String(100), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(
        Enum(
            "aberto",
            "fechamento_pendente",
            "fechado",
            name="case_status",
        ),
        default="aberto",
        nullable=False,
    )
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    storage_mode = Column(String(20), default="va", nullable=False, server_default="va")

    # Selo de fechamento da cadeia de custodia: detecta remocao do ultimo registro.
    custody_seal = Column(String(64), nullable=True)
    custody_seal_signature = Column(Text, nullable=True)
    custody_seal_record_hash = Column(String(64), nullable=True)
    custody_seal_timestamp = Column(DateTime, nullable=True)

    creator = relationship("User", foreign_keys=[created_by])
    deleter = relationship("User", foreign_keys=[deleted_by])
    assignee = relationship("User", foreign_keys=[assigned_to])
    evidences = relationship("Evidence", back_populates="case")
    shares = relationship("CaseShare", back_populates="case")
    closures = relationship("CaseClosure", back_populates="case")
