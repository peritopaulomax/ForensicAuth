"""AnalysisJob model."""

import uuid

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, JSON
from app.utils import utc_now
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("evidences.id"), nullable=False)
    technique = Column(String(50), nullable=False)
    status = Column(
        String(20),
        default="pending",
        nullable=False,
    )
    progress = Column(Integer, default=0, nullable=False)
    progress_message = Column(String(512), default="", nullable=False)
    parameters = Column(JSON, default=dict, nullable=False)
    result_path = Column(String(512))
    result_sha256 = Column(String(64))
    artifact_sha256 = Column(String(64))
    runtime_manifest = Column(JSON, default=dict)
    determinism_profile = Column(String(32))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    error_message = Column(Text)

    evidence = relationship("Evidence", back_populates="analysis_jobs")
    creator = relationship("User")
