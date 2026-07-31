"""Case closure history — immutable snapshots with system signatures."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON
from app.utils import utc_now
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class CaseClosure(Base):
    __tablename__ = "case_closures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True)
    closure_sequence = Column(Integer, nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    manifest_json = Column(JSON, nullable=False, default=dict)
    signature_mode = Column(String(20), nullable=False, default="system")
    system_signature = Column(Text, nullable=True)
    icp_signature_payload = Column(Text, nullable=True)
    signed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    signed_at = Column(DateTime, default=utc_now, nullable=False)
    custody_record_id = Column(
        UUID(as_uuid=True), ForeignKey("custody_records.id"), nullable=True
    )
    accepts_additional_signatures = Column(
        String(5), nullable=False, default="true"
    )

    case = relationship("Case", back_populates="closures")
    signer = relationship("User", foreign_keys=[signed_by])
    additional_signatures = relationship(
        "CaseClosureSignature",
        back_populates="closure",
        cascade="all, delete-orphan",
    )


class CaseClosureSignature(Base):
    __tablename__ = "case_closure_signatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    closure_id = Column(UUID(as_uuid=True), ForeignKey("case_closures.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    system_signature = Column(Text, nullable=False)
    signed_at = Column(DateTime, default=utc_now, nullable=False)

    closure = relationship("CaseClosure", back_populates="additional_signatures")
    user = relationship("User")
