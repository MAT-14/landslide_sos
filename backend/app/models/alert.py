from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import AlertKind, AlertStatus, RiskLevel
from app.models.user import utcnow


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"), index=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="risk_level", native_enum=False), default=RiskLevel.green
    )
    kind: Mapped[AlertKind] = mapped_column(
        Enum(AlertKind, name="alert_kind", native_enum=False), default=AlertKind.landslide
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status", native_enum=False), default=AlertStatus.pending
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sms_sent: Mapped[int] = mapped_column(Integer, default=0)
    sms_failed: Mapped[int] = mapped_column(Integer, default=0)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)