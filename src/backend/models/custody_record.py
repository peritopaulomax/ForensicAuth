"""CustodyRecord model — immutable audit log."""

import uuid

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, JSON
from app.utils import utc_now
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class CustodyRecord(Base):
    __tablename__ = "custody_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_type = Column(
        String(30),
        nullable=False,
    )
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    evidence_id = Column(
        UUID(as_uuid=True), ForeignKey("evidences.id", ondelete="SET NULL"), nullable=True
    )
    job_id = Column(
        UUID(as_uuid=True), ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sha256_input = Column(String(64))
    sha256_output = Column(String(64))
    sha256_params = Column(String(64))
    details = Column(JSON, default=dict)
    previous_record_hash = Column(String(64))
    record_hash = Column(String(64), nullable=False)
    chain_sequence = Column(Integer, nullable=False, default=0, index=True)
    system_signature = Column(Text, nullable=True)
    signing_key_id = Column(String(64), nullable=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False)

    case = relationship("Case")
    evidence = relationship("Evidence")
    job = relationship("AnalysisJob")
    user = relationship("User")
