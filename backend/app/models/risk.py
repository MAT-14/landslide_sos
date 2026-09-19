from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import RiskLevel
from app.models.user import utcnow


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (UniqueConstraint("zone_id", "timestamp", name="uq_risk_zone_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    probability: Mapped[float] = mapped_column(Float)
    level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="risk_level", native_enum=False)
    )
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)