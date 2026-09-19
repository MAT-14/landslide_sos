from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import RiskLevel
from app.models.user import utcnow


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    geom_wkt: Mapped[str | None] = mapped_column(Text, nullable=True)

    slope: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aspect: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elevation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lithology: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="risk_level", native_enum=False), default=RiskLevel.green
    )
    risk_probability: Mapped[float] = mapped_column(Float, default=0.0)
    rainfall_current_mm: Mapped[float] = mapped_column(Float, default=0.0)
    swi_current: Mapped[float] = mapped_column(Float, default=0.0)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def risk(self) -> RiskLevel:
        return self.risk_level

    @property
    def rainfall(self) -> float:
        return self.rainfall_current_mm

    @property
    def swi(self) -> float:
        return self.swi_current