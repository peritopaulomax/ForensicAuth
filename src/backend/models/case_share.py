"""Case sharing — controlled access for collaborators."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from app.utils import utc_now
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class CaseShare(Base):
    __tablename__ = "case_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, index=True)
    shared_with_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")
    shared_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    case = relationship("Case", back_populates="shares")
    shared_with = relationship("User", foreign_keys=[shared_with_user_id])
    sharer = relationship("User", foreign_keys=[shared_by])
