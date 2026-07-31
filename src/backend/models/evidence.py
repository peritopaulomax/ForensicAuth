"""Evidence model."""

import uuid

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Enum, JSON
from app.utils import utc_now
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Evidence(Base):
    __tablename__ = "evidences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(
        Enum("imagem", "audio", "video", "pdf", "documento", name="evidence_type"),
        nullable=False,
    )
    mime_type = Column(String(100))
    sha256 = Column(String(64), nullable=False)
    extra_metadata = Column(JSON, default=dict, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    case = relationship("Case", back_populates="evidences")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    deleter = relationship("User", foreign_keys=[deleted_by])
    analysis_jobs = relationship("AnalysisJob", back_populates="evidence", cascade="all, delete-orphan")
